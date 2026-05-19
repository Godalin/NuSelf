"""Memory-aware LangGraph-backed chat agent."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
import fcntl
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TypeAlias, TypeVar, cast

from langchain_core.tools import BaseTool

from nuself.agent.skills import AgentSkill, load_agent_skills, render_agent_skill_sections
from nuself.agent.tools import build_langchain_chat_tools
from nuself.agent.persona import (
    PersonaActivation,
    LLMBackedActivationPolicy,
    LLMBackedPersonaNode,
    LLMBackedSynthesizerNode,
    PersonaGraphDriver,
    PersonaInput,
    PersonaSynthesis,
    PersonaTurnState,
    load_persona_definitions,
)
from nuself.domain.proactive import IdeaCandidate
from nuself.config import runtime_paths
from nuself.config_system import ConfigSystem
from nuself.llm import ChatLLM, ChatMessage, default_llm
from nuself.logs import write_log_event
from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository
from nuself.persona_discussion_service import SharedPersonaDiscussionService
from nuself.trace.service import TraceRecorder

ThreadRole = Literal["user", "assistant"]
ToolServiceComponent = Literal["memory", "reflection", "reasoning", "trace"]
ConversationNodeName = Literal[
    "prepare_context",
    "persona_activation",
    "run_personas",
    "initial_response",
    "detect_tool_request",
    "execute_tool",
    "finalize_response",
    "state_update",
    "compression",
]
UpdateResult = TypeVar("UpdateResult")
USER_FACING_PERSONA_BOUNDARY = (
    "Use internal persona synthesis as private context only. "
    "Do not narrate internal persona composition or say which self contributed what in the user-facing answer, "
    "unless the user explicitly asks about the internal persona mechanism."
)
USER_FACING_PROTOCOL_BOUNDARY = (
    "The JSON object is only an internal transport protocol. "
    "The answer field must contain only the text to show to the user; "
    "do not include raw JSON, fenced code blocks, or protocol field names inside answer."
)
LOGGER = logging.getLogger(__name__)
REGENERATE_USER_FACING_RESPONSE_PROMPT = (
    "Your previous response leaked the internal response protocol into the user-visible answer. "
    "Regenerate the response using the same context. Return only the required JSON object for the runtime, "
    "and make the answer field plain user-facing text without JSON, code fences, or protocol field names."
)
PRESENTATION_BOUNDARY_FAILURE_ANSWER = "我刚刚的输出格式出了问题。请你再说一遍，我会直接用正常聊天的方式回答。"


@dataclass(frozen=True)
class ChatAgentSettings:
    """Context window settings for the chat agent."""

    recent_messages: int
    summary_trigger_messages: int
    summary_target_chars: int

    @classmethod
    def from_project(cls, project_root: Path | None = None) -> "ChatAgentSettings":
        config = ConfigSystem.load(project_root=project_root)
        return cls(
            recent_messages=config.chat.context.recent_messages,
            summary_trigger_messages=config.chat.context.summary_trigger_messages,
            summary_target_chars=config.chat.context.summary_target_chars,
        )


@dataclass(frozen=True)
class ThreadMessage:
    """A persisted user or assistant message in a NuSelf thread."""

    role: ThreadRole
    content: str
    turn_id: str | None = None

    def to_wire(self) -> dict[str, str]:
        wire = {"role": self.role, "content": self.content}
        if self.turn_id is not None:
            wire["turn_id"] = self.turn_id
        return wire

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "ThreadMessage":
        role = data.get("role")
        content = data.get("content")
        turn_id = data.get("turn_id")
        if role not in {"user", "assistant"}:
            raise ValueError("thread message role must be user or assistant")
        if not isinstance(content, str):
            raise ValueError("thread message content must be a string")
        if turn_id is not None and not isinstance(turn_id, str):
            raise ValueError("thread message turn_id must be a string when present")
        return cls(role=cast(ThreadRole, role), content=content, turn_id=turn_id)


def empty_thread_messages() -> list[ThreadMessage]:
    return []


@dataclass(frozen=True)
class ThreadState:
    """Persisted state for one chat thread."""

    thread_id: str
    summary: str = ""
    messages: list[ThreadMessage] = field(default_factory=empty_thread_messages)
    message_start_index: int = 0
    next_message_index: int = 0

    def __post_init__(self) -> None:
        if self.next_message_index == self.message_start_index and self.messages:
            object.__setattr__(self, "next_message_index", self.message_start_index + len(self.messages))

    def to_wire(self) -> dict[str, object]:
        return {
            "thread_id": self.thread_id,
            "summary": self.summary,
            "messages": [message.to_wire() for message in self.messages],
            "message_start_index": self.message_start_index,
            "next_message_index": self.next_message_index,
        }

    @classmethod
    def empty(cls, thread_id: str) -> "ThreadState":
        return cls(thread_id=thread_id)

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "ThreadState":
        thread_id = data.get("thread_id")
        summary = data.get("summary")
        messages = data.get("messages")
        message_start_index = data.get("message_start_index", 0)
        next_message_index = data.get("next_message_index")
        if not isinstance(thread_id, str):
            raise ValueError("thread_id must be a string")
        if not isinstance(summary, str):
            raise ValueError("summary must be a string")
        if not isinstance(messages, list):
            raise ValueError("messages must be a list")
        if not isinstance(message_start_index, int) or message_start_index < 0:
            raise ValueError("message_start_index must be a non-negative integer")
        message_items = cast(list[object], messages)
        parsed_messages = [
            ThreadMessage.from_wire(cast(dict[str, object], item))
            for item in message_items
            if isinstance(item, dict)
        ]
        if next_message_index is None:
            next_message_index = message_start_index + len(parsed_messages)
        if not isinstance(next_message_index, int) or next_message_index < message_start_index:
            raise ValueError("next_message_index must be an integer greater than or equal to message_start_index")
        return cls(
            thread_id=thread_id,
            summary=summary,
            messages=parsed_messages,
            message_start_index=message_start_index,
            next_message_index=next_message_index,
        )


@dataclass(frozen=True)
class ChatResult:
    """Result returned by one chat turn."""

    answer: str
    thread_id: str
    evidence_references: tuple[str, ...] = ()
    confidence: float | None = None
    epistemic_status: str = "inferred"

    @property
    def reply(self) -> str:
        return self.answer

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "answer": self.answer,
            "reply": self.answer,
            "thread_id": self.thread_id,
            "evidence_references": list(self.evidence_references),
            "epistemic_status": self.epistemic_status,
        }
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        return payload


@dataclass(frozen=True)
class DraftResponse:
    """Internal substantive response before final presentation."""

    answer: str
    evidence_references: tuple[str, ...] = ()
    confidence: float | None = None
    epistemic_status: str = "inferred"
    tool: str | None = None
    tool_args: dict[str, Any] | None = None

    @property
    def draft_answer(self) -> str:
        return self.answer


@dataclass(frozen=True)
class PresentedResponse:
    """Final user-facing response after presentation."""

    answer: str
    evidence_references: tuple[str, ...] = ()
    confidence: float | None = None
    epistemic_status: str = "inferred"


@dataclass(frozen=True)
class ConversationRuntimeResult:
    """Output from one conversation runtime turn."""

    state: ThreadState
    result: ChatResult
    node_trace: tuple[ConversationNodeName, ...] = ()


@dataclass(frozen=True)
class ConversationToolCall:
    """Detected tool call request inside one conversation turn."""

    name: str
    args: dict[str, Any]
    supported: bool
    diagnostic: str = ""


@dataclass(frozen=True)
class ConversationTurnState:
    """Typed state passed between conversation runtime nodes."""

    thread_id: str
    persisted_state: ThreadState
    user_message: str
    turn_id: str | None = None
    memory_context: str = ""
    base_messages: tuple[ThreadMessage, ...] = ()
    active_messages: tuple[ThreadMessage, ...] = ()
    persona_activation: PersonaActivation | None = None
    persona_turn_state: PersonaTurnState | None = None
    initial_response: DraftResponse | None = None
    tool_call: ConversationToolCall | None = None
    tool_result: str | None = None
    final_response: PresentedResponse | None = None
    saved_messages: tuple[ThreadMessage, ...] = ()
    updated_thread_state: ThreadState | None = None
    node_trace: tuple[ConversationNodeName, ...] = ()

    @classmethod
    def start(
        cls,
        state: ThreadState,
        message: str,
        thread_id: str,
        *,
        turn_id: str | None = None,
    ) -> "ConversationTurnState":
        return cls(thread_id=thread_id, persisted_state=state, user_message=message, turn_id=turn_id)


@dataclass(frozen=True)
class ConversationNodeResult:
    """Result from one graph-ready conversation runtime node."""

    node: ConversationNodeName
    state: ConversationTurnState


class ConversationRuntime(Protocol):
    """Runtime boundary for one conversation turn."""

    def run_turn(
        self,
        state: ThreadState,
        message: str,
        thread_id: str,
        *,
        turn_id: str | None = None,
    ) -> ConversationRuntimeResult:
        """Run one user turn and return the persisted state plus user-facing result."""
        ...


class ThreadStore:
    """File-backed chat thread store under private/threads."""

    def __init__(self, project_root: Path | None = None) -> None:
        paths = runtime_paths(project_root)
        self._threads_dir = paths.private_root / "threads"

    def load(self, thread_id: str) -> ThreadState:
        with self._locked(thread_id):
            return self._load_unlocked(thread_id)

    def save(self, state: ThreadState) -> None:
        with self._locked(state.thread_id):
            self._save_unlocked(state)

    def update(
        self,
        thread_id: str,
        update: Callable[[ThreadState], tuple[ThreadState, UpdateResult]],
    ) -> UpdateResult:
        """Atomically update one working-memory stream under an exclusive lock."""

        with self._locked(thread_id):
            state = self._load_unlocked(thread_id)
            updated, result = update(state)
            self._save_unlocked(updated)
            return result

    def _locked(self, thread_id: str) -> "_ThreadLock":
        self._threads_dir.mkdir(parents=True, exist_ok=True)
        return _ThreadLock(self._lock_path_for(thread_id))

    def _load_unlocked(self, thread_id: str) -> ThreadState:
        path = self._path_for(thread_id)
        if not path.exists():
            return ThreadState.empty(thread_id)
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"thread file must contain an object: {path}")
        return ThreadState.from_wire(cast(dict[str, object], raw))

    def _save_unlocked(self, state: ThreadState) -> None:
        self._threads_dir.mkdir(parents=True, exist_ok=True)
        path = self._path_for(state.thread_id)
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_text(json.dumps(state.to_wire(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp_path.replace(path)

    def _path_for(self, thread_id: str) -> Path:
        if thread_id == "" or "/" in thread_id or thread_id in {".", ".."}:
            raise ValueError(f"invalid thread id: {thread_id}")
        return self._threads_dir / f"{thread_id}.json"

    def _lock_path_for(self, thread_id: str) -> Path:
        if thread_id == "" or "/" in thread_id or thread_id in {".", ".."}:
            raise ValueError(f"invalid thread id: {thread_id}")
        return self._threads_dir / f"{thread_id}.lock"

    def list(self) -> list[str]:
        """List persisted thread IDs, excluding archived threads."""
        if not self._threads_dir.exists():
            return []
        ids: list[str] = []
        for path in sorted(self._threads_dir.glob("*.json")):
            ids.append(path.stem)
        return ids

    def list_archived(self) -> list[str]:
        """List archived thread IDs."""
        archived_dir = self._threads_dir / "archived"
        if not archived_dir.exists():
            return []
        ids: list[str] = []
        for path in sorted(archived_dir.glob("*.json")):
            ids.append(path.stem)
        return ids

    def rename(self, old_thread_id: str, new_thread_id: str) -> None:
        """Rename a thread file and its lock atomically."""
        if old_thread_id == new_thread_id:
            return
        old_path = self._path_for(old_thread_id)
        new_path = self._path_for(new_thread_id)
        if not old_path.exists():
            raise ValueError(f"thread not found: {old_thread_id}")
        if new_path.exists():
            raise ValueError(f"thread already exists: {new_thread_id}")
        state = self._load_unlocked(old_thread_id)
        renamed = ThreadState(
            thread_id=new_thread_id,
            summary=state.summary,
            messages=state.messages,
            message_start_index=state.message_start_index,
            next_message_index=state.next_message_index,
        )
        self._save_unlocked(renamed)
        old_path.unlink()
        old_lock = self._lock_path_for(old_thread_id)
        if old_lock.exists():
            old_lock.unlink()

    def branch(
        self,
        source_thread_id: str,
        new_thread_id: str,
        message_index: int | None = None,
    ) -> ThreadState:
        """Branch a new thread from a source thread up to a message index.

        If message_index is None, branches from the current end.
        """
        source_path = self._path_for(source_thread_id)
        new_path = self._path_for(new_thread_id)
        if not source_path.exists():
            raise ValueError(f"source thread not found: {source_thread_id}")
        if new_path.exists():
            raise ValueError(f"thread already exists: {new_thread_id}")
        source = self._load_unlocked(source_thread_id)
        if message_index is None:
            message_index = len(source.messages)
        if message_index < 0 or message_index > len(source.messages):
            raise ValueError(
                f"branch index {message_index} out of range (0..{len(source.messages)})"
            )
        branched = ThreadState(
            thread_id=new_thread_id,
            summary=source.summary,
            messages=source.messages[:message_index],
            message_start_index=source.message_start_index,
            next_message_index=source.message_start_index + message_index,
        )
        self._save_unlocked(branched)
        return branched

    def archive(self, thread_id: str) -> None:
        """Move a thread file to the archived subdirectory."""
        source_path = self._path_for(thread_id)
        if not source_path.exists():
            raise ValueError(f"thread not found: {thread_id}")
        archived_dir = self._threads_dir / "archived"
        archived_dir.mkdir(parents=True, exist_ok=True)
        target_path = archived_dir / f"{thread_id}.json"
        if target_path.exists():
            raise ValueError(f"archived thread already exists: {thread_id}")
        source_path.rename(target_path)
        old_lock = self._lock_path_for(thread_id)
        if old_lock.exists():
            old_lock.unlink()

    def unarchive(self, thread_id: str) -> None:
        """Move a thread file from the archived subdirectory back to active."""
        archived_dir = self._threads_dir / "archived"
        source_path = archived_dir / f"{thread_id}.json"
        if not source_path.exists():
            raise ValueError(f"archived thread not found: {thread_id}")
        target_path = self._path_for(thread_id)
        if target_path.exists():
            raise ValueError(f"thread already exists: {thread_id}")
        source_path.rename(target_path)

    def delete(self, thread_id: str) -> None:
        """Permanently delete a thread file and its lock."""
        path = self._path_for(thread_id)
        if not path.exists():
            raise ValueError(f"thread not found: {thread_id}")
        path.unlink()
        lock = self._lock_path_for(thread_id)
        if lock.exists():
            lock.unlink()


class _ThreadLock:
    """Advisory file lock for one working-memory stream."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file = None

    def __enter__(self) -> None:
        self._file = self._path.open("ab")
        fcntl.flock(self._file.fileno(), fcntl.LOCK_EX)

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if self._file is None:
            return
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None


class ChatAgent:
    """Memory-aware chat agent backed by a conversation runtime boundary."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        llm: ChatLLM | None = None,
        settings: ChatAgentSettings | None = None,
        thread_store: ThreadStore | None = None,
        memory_query_service: MemoryQueryService | None = None,
        runtime: ConversationRuntime | None = None,
    ) -> None:
        self._thread_store = thread_store or ThreadStore(project_root)
        self._runtime = runtime or ConversationGraphRuntime(
            project_root,
            llm=llm,
            settings=settings,
            memory_query_service=memory_query_service,
        )

    def respond(self, message: str, thread_id: str = "default", *, turn_id: str | None = None) -> ChatResult:
        def update(state: ThreadState) -> tuple[ThreadState, ChatResult]:
            completed = _completed_turn_result(state, message=message, thread_id=thread_id, turn_id=turn_id)
            if completed is not None:
                return state, completed
            runtime_result = self._runtime.run_turn(state, message, thread_id, turn_id=turn_id)
            return runtime_result.state, runtime_result.result

        return self._thread_store.update(thread_id, update)


class PresentationAgent:
    """LLM-backed final expression stage for user-facing chat replies."""

    def __init__(self, llm: ChatLLM, *, language_preference: str = "en") -> None:
        self._llm = llm
        self._language_preference = language_preference

    def present(
        self,
        draft: ParsedChatResponse,
        *,
        context_messages: tuple[ThreadMessage, ...],
        current_user_message: str,
        conversation_summary: str,
        presentation_hints: tuple[str, ...] = (),
        thread_id: str = "default",
    ) -> PresentedResponse:
        write_log_event("chat", "presentation_started", "presentation stage started", thread_id=thread_id, status="started")
        prompt = self._build_prompt(
            draft,
            context_messages=context_messages,
            current_user_message=current_user_message,
            conversation_summary=conversation_summary,
            presentation_hints=presentation_hints,
        )
        response = _to_presented_response(_parse_chat_response(self._llm.complete(prompt)))
        if not _leaks_response_protocol(response.answer):
            write_log_event(
                "chat",
                "presentation_completed",
                "presentation stage completed",
                thread_id=thread_id,
                status="completed",
                metadata={"epistemic_status": response.epistemic_status},
            )
            return response

        write_log_event(
            "chat",
            "presentation_retry",
            "presentation leaked response protocol; retrying",
            thread_id=thread_id,
            status="retry",
            metadata={"retry_reason": "protocol_leak"},
        )
        retry_prompt = [*prompt, ChatMessage(role="user", content=REGENERATE_USER_FACING_RESPONSE_PROMPT)]
        retry_response = _to_presented_response(_parse_chat_response(self._llm.complete(retry_prompt)))
        if not _leaks_response_protocol(retry_response.answer):
            write_log_event(
                "chat",
                "presentation_completed",
                "presentation stage completed after retry",
                thread_id=thread_id,
                status="completed",
                metadata={"epistemic_status": retry_response.epistemic_status, "retried": True},
            )
            return retry_response

        write_log_event(
            "chat",
            "presentation_failed",
            "presentation remained invalid after retry",
            thread_id=thread_id,
            status="failed",
            metadata={"reason": "protocol_leak"},
        )
        if _is_user_facing_safe(draft.answer):
            return _to_presented_response(draft)
        write_log_event(
            "chat",
            "presentation_failed",
            "draft fallback also violated user-facing boundary",
            thread_id=thread_id,
            status="failed",
            metadata={"reason": "draft_protocol_leak"},
        )
        return PresentedResponse(
            answer=PRESENTATION_BOUNDARY_FAILURE_ANSWER,
            evidence_references=(),
            confidence=0.0,
            epistemic_status="unsupported",
        )

    def _build_prompt(
        self,
        draft: ParsedChatResponse,
        *,
        context_messages: tuple[ThreadMessage, ...],
        current_user_message: str,
        conversation_summary: str,
        presentation_hints: tuple[str, ...],
    ) -> list[ChatMessage]:
        parts = [
            "You are the NuSelf Presentation Agent.",
            "Your job is to express an internal draft as the final user-facing answer.",
            "Return a JSON object with answer, evidence_references, confidence, and epistemic_status.",
            USER_FACING_PROTOCOL_BOUNDARY,
            USER_FACING_PERSONA_BOUNDARY,
            "Preserve the draft's factual content. Do not add new facts, memories, citations, or tool results.",
            "You may shorten, reorganize, and format the answer as readable Markdown.",
            "Keep uncertainty and epistemic status no stronger than the draft.",
        ]
        if self._language_preference != "en":
            parts.append(f"Respond to the user in {self._language_preference}.")
        if presentation_hints:
            parts.extend(["", "Presentation hints:", *[f"- {hint}" for hint in presentation_hints]])
        if conversation_summary != "":
            parts.extend(["", "Compressed conversation so far:", conversation_summary])
        parts.extend(
            [
                "",
                "Current user message:",
                current_user_message,
                "",
                "Internal draft:",
                draft.answer,
                "",
                "Draft metadata:",
                f"- evidence_references: {list(draft.evidence_references)}",
                f"- confidence: {draft.confidence}",
                f"- epistemic_status: {draft.epistemic_status}",
            ]
        )
        prompt = [ChatMessage(role="system", content="\n".join(parts))]
        for message in context_messages[-5:]:
            prompt.append(ChatMessage(role=message.role, content=message.content))
        return prompt


class ConversationGraphRuntime:
    """Graph-ready linear conversation runtime.

    The node methods below keep the current behavior explicit while giving the
    later LangGraph migration a narrow replacement boundary.
    """

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        llm: ChatLLM | None = None,
        settings: ChatAgentSettings | None = None,
        memory_query_service: MemoryQueryService | None = None,
    ) -> None:
        self._llm = llm or default_llm(project_root)
        self._settings = settings or ChatAgentSettings.from_project(project_root)
        self._project_root = project_root
        system_config = ConfigSystem.load(project_root=project_root)
        self._language_preference = system_config.chat.language_preference
        persona_definitions = load_persona_definitions(project_root)
        self._activation_policy = LLMBackedActivationPolicy(persona_definitions, llm=self._llm)
        self._presentation_agent = PresentationAgent(self._llm, language_preference=self._language_preference)
        self._persona_driver = PersonaGraphDriver(
            persona_node=LLMBackedPersonaNode(llm=self._llm, language_preference=self._language_preference),
            synthesizer_node=LLMBackedSynthesizerNode(llm=self._llm, language_preference=self._language_preference),
        )
        self._persona_discussion_service = SharedPersonaDiscussionService(
            project_root=project_root,
            llm=self._llm,
            language_preference=self._language_preference,
        )
        self._trace_recorder = TraceRecorder(project_root)
        self._memory_query_service = memory_query_service or MemoryQueryService(
            MemoryEntryRepository(project_root),
            SourceRepository(project_root),
            ProfileItemRepository(project_root),
        )
        from nuself.reflection.repository import ReflectionRepository

        self._reflection_repo = ReflectionRepository(project_root)
        tools = build_langchain_chat_tools(
            query_service=self._memory_query_service,
            reflection_repository=self._reflection_repo,
            project_root=project_root,
        )
        self._tools: dict[str, BaseTool] = {tool.name: tool for tool in tools}
        self._skills: tuple[AgentSkill, ...] = load_agent_skills()
        from nuself.agent.graph_driver import ConversationGraphDriver

        self._graph_driver = ConversationGraphDriver(self)

    def run_turn(
        self,
        state: ThreadState,
        message: str,
        thread_id: str,
        *,
        turn_id: str | None = None,
    ) -> ConversationRuntimeResult:
        turn_state = self._graph_driver.run(ConversationTurnState.start(state, message, thread_id, turn_id=turn_id))
        updated = _require_thread_state(turn_state.updated_thread_state)
        final_response = _require_presented_response(turn_state.final_response)
        self._record_chat_turn_trace(
            user_message=message,
            final_response=final_response,
            thread_id=thread_id,
            node_trace=turn_state.node_trace,
        )
        return ConversationRuntimeResult(
            state=updated,
            result=ChatResult(
                answer=final_response.answer,
                thread_id=thread_id,
                evidence_references=final_response.evidence_references,
                confidence=final_response.confidence,
                epistemic_status=final_response.epistemic_status,
            ),
            node_trace=turn_state.node_trace,
        )

    def _record_chat_turn_trace(
        self,
        *,
        user_message: str,
        final_response: PresentedResponse,
        thread_id: str,
        node_trace: tuple[ConversationNodeName, ...],
    ) -> None:
        if not final_response.evidence_references:
            return
        evidence_refs = list(final_response.evidence_references)
        try:
            self._trace_recorder.record_chat_turn(
                title=f"Chat turn cited {evidence_refs[0]}",
                summary="Assistant reply used retrieved context cited by the final response.",
                user_input=_trace_summary(user_message),
                assistant_output=_trace_summary(final_response.answer),
                thread_id=thread_id,
                evidence_refs=evidence_refs,
                participants=["chat_agent", "presentation_agent"],
                decision_points=["Recorded because the final response cited evidence references."],
                metadata={"node_trace": list(node_trace), "epistemic_status": final_response.epistemic_status},
            )
        except Exception as exc:
            write_log_event(
                "memory",
                "trace_write_failed",
                "chat trace write failed",
                project_root=self._project_root,
                thread_id=thread_id,
                status="error",
                metadata={"error": str(exc)},
            )

    def prepare_context_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        base_messages = tuple(_drop_local_fallback_replies(state.persisted_state.messages))
        active_messages = (*base_messages, ThreadMessage(role="user", content=state.user_message, turn_id=state.turn_id))
        packed_memory = self._memory_query_service.pack(MemoryQuery(text=state.user_message))
        return ConversationNodeResult(
            node="prepare_context",
            state=replace(
                state,
                base_messages=base_messages,
                active_messages=active_messages,
                memory_context=packed_memory.text,
                node_trace=(*state.node_trace, "prepare_context"),
            ),
        )

    def persona_activation_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        activation = self._activation_policy.decide(
            PersonaInput(user_message=state.user_message, memory_context=state.memory_context)
        )
        persona_turn_state = None
        if activation.activated:
            persona_turn_state = PersonaTurnState(
                input=PersonaInput(user_message=state.user_message, memory_context=state.memory_context),
                selected_personas=activation.selected_personas,
            )
        return ConversationNodeResult(
            node="persona_activation",
            state=replace(
                state,
                persona_activation=activation,
                persona_turn_state=persona_turn_state,
                node_trace=(*state.node_trace, "persona_activation"),
            ),
        )

    def run_personas_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        persona_turn_state = _require_persona_turn_state(state.persona_turn_state)
        updated_persona_turn_state = self._persona_driver.run(persona_turn_state)
        activation = state.persona_activation
        trigger = activation.trigger if activation is not None else "activated"
        try:
            write_log_event(
                "persona",
                "persona_summary",
                _compact_persona_summary(updated_persona_turn_state),
                project_root=self._project_root,
                thread_id=state.thread_id,
                status=trigger,
                metadata={
                    "persona_count": len(updated_persona_turn_state.contributions),
                    "has_synthesis": updated_persona_turn_state.synthesis is not None,
                },
            )
        except Exception:
            LOGGER.exception("failed to write persona summary log")
        activation = state.persona_activation
        should_escalate = activation.should_escalate if activation is not None else False
        escalation_reason = activation.escalation_reason if activation is not None else "no activation"
        try:
            write_log_event(
                "persona",
                "host_discussion_decision",
                escalation_reason,
                project_root=self._project_root,
                thread_id=state.thread_id,
                status="approved" if should_escalate else "skipped",
                metadata={
                    "should_escalate": should_escalate,
                    "escalation_reason": escalation_reason,
                },
            )
        except Exception:
            LOGGER.exception("failed to write host discussion decision log")
        # Host decision is the only gate for entering competitive discussion.
        try:
            if should_escalate:
                # Build a lightweight IdeaCandidate from the chat turn.
                lines = state.user_message.splitlines()
                title = (lines[0] if lines else state.user_message)[:120]
                result = self._persona_discussion_service.discuss(
                    self._build_chat_discussion_candidate(
                        thread_id=state.thread_id,
                        user_message=state.user_message,
                        title=title,
                        source_summary=updated_persona_turn_state.synthesis.summary if updated_persona_turn_state.synthesis is not None else "",
                    ),
                    on_trace_entry=lambda entry: self._write_persona_discussion_step_log(
                        state.thread_id,
                        trigger,
                        entry,
                    ),
                )
                # Log and REPL-print discussion outcome
                try:
                    write_log_event(
                        "persona",
                        "persona_discussion",
                        f"chat-triggered discussion: {result.reason}",
                        project_root=self._project_root,
                        thread_id=state.thread_id,
                        status=trigger,
                        metadata={
                            "winner_persona_ids": list(result.winner_persona_ids),
                            "emergent_persona_ids": list(result.emergent_persona_ids),
                            "blocking_vetos": list(result.blocking_vetos),
                            "reason": result.reason,
                            "discussion_steps": len(result.discussion_trace),
                        },
                    )
                except Exception:
                    LOGGER.exception("failed to write persona discussion log")
        except Exception:
            # Keep chat robust: failures in discussion should not break response
            LOGGER.exception("persona discussion failed during chat turn")
        return ConversationNodeResult(
            node="run_personas",
            state=replace(
                state,
                persona_turn_state=updated_persona_turn_state,
                node_trace=(*state.node_trace, "run_personas"),
            ),
        )

    def _build_chat_discussion_candidate(
        self,
        *,
        thread_id: str,
        user_message: str,
        title: str,
        source_summary: str,
    ) -> IdeaCandidate:
        ctype = "question" if "?" in user_message else "action"
        return IdeaCandidate(
            id=f"chat-{thread_id}-{int(datetime.now(UTC).timestamp())}",
            title=title,
            body=user_message,
            candidate_type=ctype,  # type: ignore[arg-type]
            confidence=0.8,
            novelty=0.5,
            urgency=0.2,
            interruption_cost=0.1,
            evidence_refs=(),
            suggested_thread_id=thread_id,
            source_summary=source_summary,
            created_at=datetime.now(UTC).isoformat(),
        )

    def initial_response_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        if state.persona_turn_state is not None and state.persona_turn_state.synthesis is not None:
            response = self._synthesize_response(state)
        else:
            prompt = self._build_prompt(state)
            response = _parse_chat_response(self._llm.complete(prompt))
        return ConversationNodeResult(
            node="initial_response",
            state=replace(
                state,
                initial_response=response,
                node_trace=(*state.node_trace, "initial_response"),
            ),
        )

    def detect_tool_request_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        response = _require_chat_response(state.initial_response)
        tool_call = self._detect_tool_call(response)
        return ConversationNodeResult(
            node="detect_tool_request",
            state=replace(
                state,
                tool_call=tool_call,
                node_trace=(*state.node_trace, "detect_tool_request"),
            ),
        )

    def execute_tool_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        response = _require_chat_response(state.initial_response)
        tool_result = self._invoke_tool(response)
        tool_message = ThreadMessage(
            role="assistant",
            content=f"[Tool call: {response.tool}]\n{tool_result}",
        )
        messages_with_tool = (*state.active_messages, tool_message)
        return ConversationNodeResult(
            node="execute_tool",
            state=replace(
                state,
                tool_result=tool_result,
                saved_messages=messages_with_tool,
                node_trace=(*state.node_trace, "execute_tool"),
            ),
        )

    def finalize_response_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        if _is_supported_tool_call(state.tool_call):
            tool_result = _require_tool_result(state.tool_result)
            follow_up_prompt = self._build_follow_up_prompt(
                ThreadState(
                    thread_id=state.thread_id,
                    summary=state.persisted_state.summary,
                    messages=list(state.saved_messages),
                ),
                tool_result,
            )
            draft_response = _parse_chat_response(self._llm.complete(follow_up_prompt))
            final_response = _apply_unsupported_claim_guard(
                self._presentation_agent.present(
                    draft_response,
                    context_messages=state.saved_messages,
                    current_user_message=state.user_message,
                    conversation_summary=state.persisted_state.summary,
                    presentation_hints=_presentation_hints(state.user_message),
                    thread_id=state.thread_id,
                )
            )
            saved_messages = (
                *state.saved_messages,
                ThreadMessage(role="assistant", content=final_response.answer, turn_id=state.turn_id),
            )
        else:
            response = _require_chat_response(state.initial_response)
            final_response = _apply_unsupported_claim_guard(
                self._presentation_agent.present(
                    response,
                    context_messages=state.active_messages,
                    current_user_message=state.user_message,
                    conversation_summary=state.persisted_state.summary,
                    presentation_hints=_presentation_hints(state.user_message),
                    thread_id=state.thread_id,
                )
            )
            saved_messages = (
                *state.active_messages,
                ThreadMessage(role="assistant", content=final_response.answer, turn_id=state.turn_id),
            )
        return ConversationNodeResult(
            node="finalize_response",
            state=replace(
                state,
                final_response=final_response,
                saved_messages=saved_messages,
                node_trace=(*state.node_trace, "finalize_response"),
            ),
        )

    def _detect_tool_call(self, response: ParsedChatResponse) -> ConversationToolCall | None:
        if response.tool is None:
            return None
        tool_args = response.tool_args if response.tool_args is not None else {}
        if response.tool not in self._tools:
            return ConversationToolCall(
                name=response.tool,
                args=tool_args,
                supported=False,
                diagnostic=f"unsupported tool request: {response.tool}",
            )
        return ConversationToolCall(name=response.tool, args=tool_args, supported=True)

    def state_update_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        updated = ThreadState(
            thread_id=state.thread_id,
            summary=state.persisted_state.summary,
            messages=list(state.saved_messages),
            message_start_index=state.persisted_state.message_start_index,
            next_message_index=(
                state.persisted_state.next_message_index + len(state.saved_messages) - len(state.base_messages)
            ),
        )
        return ConversationNodeResult(
            node="state_update",
            state=replace(
                state,
                updated_thread_state=updated,
                node_trace=(*state.node_trace, "state_update"),
            ),
        )

    def compression_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        updated = _require_thread_state(state.updated_thread_state)
        return ConversationNodeResult(
            node="compression",
            state=replace(
                state,
                updated_thread_state=self._compress_if_needed(updated),
                node_trace=(*state.node_trace, "compression"),
            ),
        )

    def _build_prompt(self, state: ConversationTurnState) -> list[ChatMessage]:
        synthesis = None
        if state.persona_turn_state is not None:
            synthesis = state.persona_turn_state.synthesis
        prompt: list[ChatMessage] = [ChatMessage(role="system", content=self._system_prompt(state, synthesis))]
        for message in state.active_messages[-self._settings.recent_messages :]:
            prompt.append(ChatMessage(role=message.role, content=message.content))
        return prompt

    def _synthesize_response(self, state: ConversationTurnState) -> ParsedChatResponse:
        """Generate the user-facing response from persona contributions."""
        synthesis = _require_synthesis(state.persona_turn_state)
        parts: list[str] = [
            "You are the synthesizer self of NuSelf. Fuse the following internal persona perspectives into a single, coherent user-facing response.",
            "Return a JSON object with answer, evidence_references, confidence, and epistemic_status.",
            "answer must be the user-facing text. evidence_references must cite relevant memory ids or source refs when available.",
            USER_FACING_PERSONA_BOUNDARY,
            USER_FACING_PROTOCOL_BOUNDARY,
            "If you make a claim about the user's preferences, history, or other personal facts without evidence, set epistemic_status to unsupported.",
            "confidence should be a number between 0 and 1 when you can estimate it; otherwise omit it.",
            "epistemic_status should be one of grounded, inferred, uncertain, or unsupported.",
        ]
        if self._language_preference != "en":
            parts.append(f"Respond to the user in {self._language_preference}.")
        if state.memory_context != "":
            parts.extend(["", "Relevant memory context:", state.memory_context])
        if state.persisted_state.summary != "":
            parts.extend(["", "Compressed conversation so far:", state.persisted_state.summary])
        parts.extend(["", "Persona contributions:"])
        for contrib in state.persona_turn_state.contributions if state.persona_turn_state is not None else ():
            note = contrib.notes[0] if contrib.notes else ""
            parts.append(f"- {contrib.persona_id}: {note}")
        parts.extend([
            "",
            "Internal perspective fusion:",
            f"Summary: {synthesis.summary}",
            f"Perspectives involved: {', '.join(synthesis.source_personas)}",
        ])
        parts.extend(_tool_prompt_sections(self._tools.values(), self._skills))
        prompt: list[ChatMessage] = [ChatMessage(role="system", content="\n".join(parts))]
        for message in state.active_messages[-self._settings.recent_messages :]:
            prompt.append(ChatMessage(role=message.role, content=message.content))
        return _parse_chat_response(self._llm.complete(prompt))

    def _build_follow_up_prompt(self, state: ThreadState, tool_result: str) -> list[ChatMessage]:
        """Build a prompt for the follow-up after tool invocation."""
        follow_up_system = (
            "You are NuSelf. The previous tool call returned the following results. "
            "Use these results to generate your final answer. "
            "Return a JSON object with answer, evidence_references, confidence, and epistemic_status. "
            f"{USER_FACING_PROTOCOL_BOUNDARY}"
        )
        if self._language_preference != "en":
            follow_up_system += f"\n\nRespond to the user in {self._language_preference}."
        prompt: list[ChatMessage] = [
            ChatMessage(
                role="system",
                content=follow_up_system,
            )
        ]
        # Include recent message history
        for message in state.messages[-self._settings.recent_messages :]:
            prompt.append(ChatMessage(role=message.role, content=message.content))
        # Add tool result
        prompt.append(ChatMessage(role="user", content=f"Tool result:\n{tool_result}"))
        return prompt

    def _system_prompt(self, state: ConversationTurnState, synthesis: "PersonaSynthesis | None" = None) -> str:
        parts = [
            "You are NuSelf, a private AI mirror for one person.",
            "Use the user's memory entries and source chunks as durable context. Do not invent memories.",
            "Return a JSON object with answer, evidence_references, confidence, and epistemic_status.",
            "answer must be the user-facing text. evidence_references must cite relevant memory ids or source refs when available.",
            USER_FACING_PERSONA_BOUNDARY,
            USER_FACING_PROTOCOL_BOUNDARY,
            "If you make a claim about the user's preferences, history, or other personal facts without evidence, set epistemic_status to unsupported.",
            "confidence should be a number between 0 and 1 when you can estimate it; otherwise omit it.",
            "epistemic_status should be one of grounded, inferred, uncertain, or unsupported.",
            "Answer directly, keep uncertainty explicit, and surface useful questions when appropriate.",
        ]
        if self._language_preference != "en":
            parts.append(f"Respond to the user in {self._language_preference}.")
        if state.memory_context != "":
            parts.extend(["", "Relevant memory context:", state.memory_context])
        if state.persisted_state.summary != "":
            parts.extend(["", "Compressed conversation so far:", state.persisted_state.summary])
        if synthesis is not None:
            parts.extend(["", "Internal perspective fusion:", f"Summary: {synthesis.summary}", f"Perspectives involved: {', '.join(synthesis.source_personas)}"])

        parts.extend(_tool_prompt_sections(self._tools.values(), self._skills))
        return "\n".join(parts)

    def _compress_if_needed(self, state: ThreadState) -> ThreadState:
        if len(state.messages) <= self._settings.summary_trigger_messages:
            return state
        recent = state.messages[-self._settings.recent_messages :]
        older = state.messages[: -self._settings.recent_messages]
        summary = self._summarize(state.summary, older)
        return ThreadState(
            thread_id=state.thread_id,
            summary=summary,
            messages=recent,
            message_start_index=state.next_message_index - len(recent),
            next_message_index=state.next_message_index,
        )

    def _invoke_tool(self, tool: ParsedChatResponse) -> str:
        """Execute a tool call and return the result."""
        if tool.tool is None or tool.tool not in self._tools:
            return f"Error: unknown tool {tool.tool}"

        tool_args_input = tool.tool_args if tool.tool_args is not None else {}
        service_component = _tool_service_component(tool.tool)

        try:
            tool_obj = self._tools[tool.tool]
            invoke = cast(Callable[[dict[str, Any]], object], getattr(tool_obj, "invoke"))
            result = str(invoke(tool_args_input))
            if service_component is not None:
                self._write_service_tool_log(tool.tool, service_component, "completed")
            return result
        except TypeError as e:
            if service_component is not None:
                self._write_service_tool_log(tool.tool, service_component, "failed", error=str(e))
            return f"Error invoking {tool.tool}: {e}"
        except Exception as e:
            if service_component is not None:
                self._write_service_tool_log(tool.tool, service_component, "failed", error=str(e))
            return f"Error: {e}"

    def _write_service_tool_log(
        self,
        tool_name: str,
        service_component: ToolServiceComponent,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        write_log_event(
            "chat",
            "service_tool_called",
            f"chat called {service_component} service tool {tool_name}",
            project_root=self._project_root,
            status=status,
            error=error,
            metadata={"service_component": service_component, "tool": tool_name},
        )

    def _write_persona_discussion_step_log(self, thread_id: str, trigger: str, entry: str) -> None:
        try:
            write_log_event(
                "persona",
                "persona_discussion_step",
                "",
                project_root=self._project_root,
                thread_id=thread_id,
                status=trigger,
                metadata={"discussion_trace": [entry]},
            )
        except Exception:
            LOGGER.exception("failed to write persona discussion step log")

    def _summarize(self, previous_summary: str, messages: list[ThreadMessage]) -> str:
        transcript = "\n".join(f"{message.role}: {message.content}" for message in messages)
        prompt = [
            ChatMessage(
                role="system",
                content=(
                    "Compress a private NuSelf conversation into durable context. "
                    "Preserve user preferences, decisions, unresolved questions, and useful facts. "
                    "Do not add new facts."
                ),
            ),
            ChatMessage(
                role="user",
                content=f"Previous summary:\n{previous_summary or '(none)'}\n\nNew transcript:\n{transcript}",
            ),
        ]
        try:
            summary = self._llm.complete(prompt).strip()
        except RuntimeError:
            summary = _local_summary(previous_summary, transcript, self._settings.summary_target_chars)
        return summary[: self._settings.summary_target_chars]


def _local_summary(previous_summary: str, transcript: str, target_chars: int) -> str:
    combined = "\n\n".join(part for part in [previous_summary, transcript] if part != "")
    if len(combined) <= target_chars:
        return combined
    return combined[-target_chars:]


def _compact_persona_summary(turn_state: "PersonaTurnState") -> str:
    parts: list[str] = []
    for contrib in turn_state.contributions:
        note = contrib.notes[0] if contrib.notes else ""
        snippet = note if len(note) <= 140 else (note[:137] + "...")
        parts.append(f"{contrib.persona_id}: {snippet}")
    if turn_state.synthesis is not None:
        summary = turn_state.synthesis.summary
        synthesis_snippet = summary if len(summary) <= 140 else (summary[:137] + "...")
        parts.append(f"synthesizer_self: {synthesis_snippet}")
    if not parts:
        return "(no persona contributions)"
    return "\n".join(parts)


def _trace_summary(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _drop_local_fallback_replies(messages: list[ThreadMessage]) -> list[ThreadMessage]:
    return [message for message in messages if not _is_local_fallback_reply(message)]


def _is_local_fallback_reply(message: ThreadMessage) -> bool:
    return message.role == "assistant" and message.content.startswith("LLM API is not configured yet.")


def _require_chat_response(response: ParsedChatResponse | None) -> ParsedChatResponse:
    if response is None:
        raise RuntimeError("conversation runtime response is missing")
    return response


def _require_thread_state(state: ThreadState | None) -> ThreadState:
    if state is None:
        raise RuntimeError("conversation runtime thread state is missing")
    return state


def _completed_turn_result(
    state: ThreadState,
    *,
    message: str,
    thread_id: str,
    turn_id: str | None,
) -> ChatResult | None:
    if turn_id is None or len(state.messages) < 2:
        return None
    assistant_message: ThreadMessage | None = None
    for item in reversed(state.messages):
        if item.turn_id == turn_id and item.role == "assistant":
            assistant_message = item
            break
    if assistant_message is None:
        return None
    for item in reversed(state.messages):
        if item.turn_id == turn_id and item.role == "user":
            if item.content == message:
                return ChatResult(answer=assistant_message.content, thread_id=thread_id)
            return None
    return None


def _require_presented_response(response: PresentedResponse | None) -> PresentedResponse:
    if response is None:
        raise RuntimeError("conversation runtime presented response is missing")
    return response


def _require_persona_turn_state(state: PersonaTurnState | None) -> PersonaTurnState:
    if state is None:
        raise RuntimeError("conversation runtime persona turn state is missing")
    return state


def _require_synthesis(state: PersonaTurnState | None) -> PersonaSynthesis:
    if state is None or state.synthesis is None:
        raise RuntimeError("conversation runtime synthesis is missing")
    return state.synthesis


def _require_tool_result(tool_result: str | None) -> str:
    if tool_result is None:
        raise RuntimeError("conversation runtime tool result is missing")
    return tool_result


def _is_supported_tool_call(tool_call: ConversationToolCall | None) -> bool:
    return tool_call is not None and tool_call.supported


def _tool_service_component(tool_name: str) -> ToolServiceComponent | None:
    if tool_name in {"search_memory", "archive_memory", "update_memory_importance"}:
        return "memory"
    if tool_name in {"list_pending_reflections", "dismiss_reflection", "archive_reflection"}:
        return "reflection"
    if tool_name in {"list_active_reasoning_threads", "show_reasoning_thread"}:
        return "reasoning"
    if tool_name in {"search_trace", "show_trace"}:
        return "trace"
    return None


def _tool_prompt_sections(tools: "Iterable[BaseTool]", skills: tuple[AgentSkill, ...]) -> list[str]:
    lines = [
        "",
        "Available tools:",
        "The following LangChain tools are loaded in the current NuSelf runtime.",
        'You may invoke a tool by including a "tool" field in your JSON:',
        '{"answer": "...", "tool": "search_memory", "tool_args": {"query": "search term"}, ...}',
        "The tool result will be injected back into context before your final answer.",
        "If the user asks whether memory tools are available, answer from this loaded tool list.",
        "Tools available:",
    ]
    for tool in tools:
        args = _tool_args_signature(tool)
        lines.append(f"- {tool.name}({args}): {tool.description}")
    lines.extend(render_agent_skill_sections(skills))
    return lines


def _tool_args_signature(tool: BaseTool) -> str:
    args_schema = cast(object, getattr(tool, "args", {}))
    if not isinstance(args_schema, dict):
        return ""
    pieces: list[str] = []
    for name, schema in cast(dict[object, object], args_schema).items():
        if not isinstance(name, str):
            continue
        type_name = "object"
        default: object | None = None
        if isinstance(schema, dict):
            schema_dict = cast(dict[object, object], schema)
            type_value = schema_dict.get("type")
            if isinstance(type_value, str):
                type_name = type_value
            default = schema_dict.get("default")
        if default is None:
            pieces.append(f"{name}: {type_name}")
        else:
            pieces.append(f"{name}: {type_name} = {default!r}")
    return ", ".join(pieces)


ParsedChatResponse: TypeAlias = DraftResponse
_PROTOCOL_FIELD_NAMES = ("answer", "evidence_references", "confidence", "epistemic_status")


def _parse_chat_response(raw: str) -> ParsedChatResponse:
    stripped = raw.strip()
    protocol_json = _extract_protocol_json(stripped)
    if protocol_json is not None:
        try:
            parsed: object = json.loads(protocol_json)
        except json.JSONDecodeError:
            return ParsedChatResponse(answer=raw)
        if isinstance(parsed, dict):
            data = cast(dict[str, object], parsed)
            answer = data.get("answer")
            if not isinstance(answer, str) or answer.strip() == "":
                return ParsedChatResponse(answer=raw)
            evidence_references = _string_tuple(data.get("evidence_references"))
            confidence = _optional_float(data.get("confidence"))
            epistemic_status = _string_field(data.get("epistemic_status"), default="inferred") or "inferred"
            tool = _string_field(data.get("tool"))
            tool_args_raw = data.get("tool_args")
            tool_args = cast(dict[str, Any], tool_args_raw) if isinstance(tool_args_raw, dict) else None
            return ParsedChatResponse(
                answer=answer,
                evidence_references=evidence_references,
                confidence=confidence,
                epistemic_status=epistemic_status,
                tool=tool,
                tool_args=tool_args,
            )
    markdown_response = _parse_markdown_chat_response(raw)
    if markdown_response is not None:
        return markdown_response
    return ParsedChatResponse(answer=raw)


def _extract_protocol_json(text: str) -> str | None:
    if text.startswith("{"):
        return text
    if not text.startswith("```"):
        return None
    lines = text.splitlines()
    if len(lines) < 3:
        return None
    fence = lines[0].strip().casefold()
    if fence not in {"```", "```json"}:
        return None
    closing_index = _closing_fence_index(lines)
    if closing_index is None:
        return None
    body = "\n".join(lines[1:closing_index]).strip()
    if not body.startswith("{"):
        return None
    return body


def _closing_fence_index(lines: list[str]) -> int | None:
    for index in range(len(lines) - 1, 0, -1):
        if lines[index].strip() == "```":
            return index
    return None


def _to_presented_response(response: ParsedChatResponse) -> PresentedResponse:
    return PresentedResponse(
        answer=response.answer,
        evidence_references=response.evidence_references,
        confidence=response.confidence,
        epistemic_status=response.epistemic_status,
    )


def _leaks_response_protocol(answer: str) -> bool:
    stripped = answer.strip()
    if stripped.startswith("```"):
        return True
    if stripped.startswith("{") and _contains_protocol_field(stripped):
        return True
    if _starts_with_persona_attribution(stripped):
        return True
    lowered = stripped[:4000].casefold()
    return sum(1 for field_name in _PROTOCOL_FIELD_NAMES if field_name in lowered) >= 2


def _contains_protocol_field(text: str) -> bool:
    lowered = text[:4000].casefold()
    for field_name in _PROTOCOL_FIELD_NAMES:
        if f'"{field_name}"' in lowered or f"{field_name}:" in lowered:
            return True
    return False


def _is_user_facing_safe(answer: str) -> bool:
    return not _leaks_response_protocol(answer)


def _starts_with_persona_attribution(text: str) -> bool:
    prefixes = ("(", "（")
    stripped = text.strip()
    if not stripped.startswith(prefixes):
        return False
    head = stripped[:240]
    return "_self" in head and (")" in head or "）" in head)


def _presentation_hints(user_message: str) -> tuple[str, ...]:
    normalized = user_message.casefold()
    hints: list[str] = []
    if any(marker in normalized for marker in ("简单", "短", "太多", "想不过来", "simple", "short", "too much")):
        hints.append("The user is asking for a shorter, simpler answer. Prefer compression and one concrete next step.")
    return tuple(hints)


def _parse_markdown_chat_response(raw: str) -> ParsedChatResponse | None:
    lines = raw.strip().splitlines()
    fields: dict[str, list[str]] = {}
    preface: list[str] = []
    current_field: str | None = None
    saw_structured_field = False
    for line in lines:
        field_name, value = _markdown_response_field(line)
        if field_name is not None:
            saw_structured_field = True
            current_field = field_name
            fields.setdefault(field_name, [])
            if value:
                fields[field_name].append(value)
            continue
        if current_field is None:
            preface.append(line)
        else:
            fields[current_field].append(line)
    answer_lines = fields.get("answer")
    if not saw_structured_field or not answer_lines:
        return None
    answer = "\n".join([*preface, *answer_lines]).strip()
    if answer == "":
        return None
    return ParsedChatResponse(
        answer=answer,
        evidence_references=_parse_markdown_evidence_references("\n".join(fields.get("evidence_references", []))),
        confidence=_optional_float("\n".join(fields.get("confidence", []))),
        epistemic_status=(
            _string_field("\n".join(fields.get("epistemic_status", [])).strip(), default="inferred") or "inferred"
        ),
        tool=_string_field("\n".join(fields.get("tool", [])).strip()),
    )


def _markdown_response_field(line: str) -> tuple[str | None, str]:
    left, separator, right = line.partition(":")
    if not separator:
        return (None, "")
    normalized = left.strip().strip("*").strip().casefold()
    normalized = normalized.replace("-", "_").replace(" ", "_")
    if normalized in {"answer", "evidence_references", "confidence", "epistemic_status", "tool"}:
        return (normalized, right.strip())
    return (None, "")


def _parse_markdown_evidence_references(value: str) -> tuple[str, ...]:
    stripped = value.strip()
    if stripped == "":
        return ()
    if stripped.startswith("[") and stripped.endswith("]"):
        stripped = stripped[1:-1].strip()
    if stripped == "":
        return ()
    return tuple(part.strip().strip("\"'") for part in stripped.split(",") if part.strip())


def _apply_unsupported_claim_guard(response: PresentedResponse) -> PresentedResponse:
    if response.evidence_references:
        return response
    if not _looks_like_personal_claim(response.answer):
        return response
    confidence = response.confidence if response.confidence is not None else 0.25
    return PresentedResponse(
        answer=response.answer,
        evidence_references=response.evidence_references,
        confidence=min(confidence, 0.25),
        epistemic_status="unsupported",
    )


def _looks_like_personal_claim(answer: str) -> bool:
    normalized = answer.casefold()
    claim_markers = (
        "you ",
        "your ",
        "remember",
        "prefer",
        "like",
        "believe",
        "think",
        "previously",
        "earlier",
        "always",
        "never",
        "history",
        "memory",
    )
    return any(marker in normalized for marker in claim_markers)


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    result: list[str] = []
    for item in cast(list[object], value):
        if isinstance(item, str) and item.strip() != "":
            result.append(item.strip())
    return tuple(result)


def _optional_float(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and value.strip() != "":
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _string_field(value: object, *, default: str | None = None) -> str | None:
    if isinstance(value, str) and value.strip() != "":
        return value
    return default
