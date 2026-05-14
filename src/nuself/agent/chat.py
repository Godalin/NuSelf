"""Memory-aware LangGraph-backed chat agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
import fcntl
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar, cast

from nuself.agent.tools import MemorySearchTool
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
from nuself.tui.render import render_discussion_trace, render_host_decision

ThreadRole = Literal["user", "assistant"]
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

    def to_wire(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "ThreadMessage":
        role = data.get("role")
        content = data.get("content")
        if role not in {"user", "assistant"}:
            raise ValueError("thread message role must be user or assistant")
        if not isinstance(content, str):
            raise ValueError("thread message content must be a string")
        return cls(role=cast(ThreadRole, role), content=content)


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
    memory_context: str = ""
    base_messages: tuple[ThreadMessage, ...] = ()
    active_messages: tuple[ThreadMessage, ...] = ()
    persona_activation: PersonaActivation | None = None
    persona_turn_state: PersonaTurnState | None = None
    initial_response: ParsedChatResponse | None = None
    tool_call: ConversationToolCall | None = None
    tool_result: str | None = None
    final_response: ParsedChatResponse | None = None
    saved_messages: tuple[ThreadMessage, ...] = ()
    updated_thread_state: ThreadState | None = None
    node_trace: tuple[ConversationNodeName, ...] = ()

    @classmethod
    def start(cls, state: ThreadState, message: str, thread_id: str) -> "ConversationTurnState":
        return cls(thread_id=thread_id, persisted_state=state, user_message=message)


@dataclass(frozen=True)
class ConversationNodeResult:
    """Result from one graph-ready conversation runtime node."""

    node: ConversationNodeName
    state: ConversationTurnState


class ConversationRuntime(Protocol):
    """Runtime boundary for one conversation turn."""

    def run_turn(self, state: ThreadState, message: str, thread_id: str) -> ConversationRuntimeResult:
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
        self._file = self._path.open("a+b")
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

    def respond(self, message: str, thread_id: str = "default") -> ChatResult:
        def update(state: ThreadState) -> tuple[ThreadState, ChatResult]:
            runtime_result = self._runtime.run_turn(state, message, thread_id)
            return runtime_result.state, runtime_result.result

        return self._thread_store.update(thread_id, update)


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
        self._persona_driver = PersonaGraphDriver(
            persona_node=LLMBackedPersonaNode(llm=self._llm),
            synthesizer_node=LLMBackedSynthesizerNode(llm=self._llm),
        )
        self._persona_discussion_service = SharedPersonaDiscussionService(project_root=project_root, llm=self._llm)
        self._memory_query_service = memory_query_service or MemoryQueryService(
            MemoryEntryRepository(project_root),
            SourceRepository(project_root),
            ProfileItemRepository(project_root),
        )
        from nuself.agent.tools import DismissReflectionTool, ListPendingReflectionsTool

        from nuself.agent.tools import (
            ArchiveMemoryTool,
            ArchiveReflectionTool,
            DismissReflectionTool,
            ListPendingReflectionsTool,
            UpdateMemoryImportanceTool,
        )
        from nuself.reflection.repository import ReflectionRepository

        self._reflection_repo = ReflectionRepository(project_root)
        self._tools: dict[str, Any] = {
            "search_memory": MemorySearchTool(query_service=self._memory_query_service),
            "list_pending_reflections": ListPendingReflectionsTool(repository=self._reflection_repo),
            "dismiss_reflection": DismissReflectionTool(repository=self._reflection_repo),
            "archive_reflection": ArchiveReflectionTool(repository=self._reflection_repo),
            "archive_memory": ArchiveMemoryTool(project_root=project_root),
            "update_memory_importance": UpdateMemoryImportanceTool(project_root=project_root),
        }
        from nuself.agent.graph_driver import ConversationGraphDriver

        self._graph_driver = ConversationGraphDriver(self)

    def run_turn(self, state: ThreadState, message: str, thread_id: str) -> ConversationRuntimeResult:
        turn_state = self._graph_driver.run(ConversationTurnState.start(state, message, thread_id))
        updated = _require_thread_state(turn_state.updated_thread_state)
        final_response = _require_chat_response(turn_state.final_response)
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

    def prepare_context_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        base_messages = tuple(_drop_local_fallback_replies(state.persisted_state.messages))
        active_messages = (*base_messages, ThreadMessage(role="user", content=state.user_message))
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
            pass
        # Immediate REPL/console visibility for interactive debugging and UX:
        try:
            print(f"--- Persona Trigger: {trigger} (selected={len(updated_persona_turn_state.selected_personas)}) ---")
            for contrib in updated_persona_turn_state.contributions:
                note = contrib.notes[0] if contrib.notes else "(no note)"
                print(f"{contrib.persona_id}: {note}")
            if updated_persona_turn_state.synthesis is not None:
                print("--- Persona Synthesis ---")
                print(updated_persona_turn_state.synthesis.summary)
                print("--- End Persona Synthesis ---")
        except Exception:
            pass
        activation = state.persona_activation
        should_escalate = activation.should_escalate if activation is not None else False
        escalation_reason = activation.escalation_reason if activation is not None else "no activation"
        host_decision_event = None
        try:
            host_decision_event = write_log_event(
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
            host_decision_event = None
        try:
            if host_decision_event is not None:
                for line in render_host_decision(host_decision_event):
                    print(line)
            else:
                print(f"--- Host Decision: {'escalate' if should_escalate else 'skip'} ({escalation_reason}) ---")
        except Exception:
            pass
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
                    )
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
                        },
                    )
                except Exception:
                    pass
                try:
                    print("=== Chat-triggered Persona Discussion ===")
                    for line in render_discussion_trace(list(result.discussion_trace), title="discussion trace"):
                        print(line)
                    print("=== End Discussion ===")
                except Exception:
                    pass
        except Exception:
            # Keep chat robust: failures in discussion should not break response
            pass
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
            final_response = _apply_unsupported_claim_guard(_parse_chat_response(self._llm.complete(follow_up_prompt)))
            saved_messages = (*state.saved_messages, ThreadMessage(role="assistant", content=final_response.answer))
        else:
            response = _require_chat_response(state.initial_response)
            final_response = _apply_unsupported_claim_guard(response)
            saved_messages = (*state.active_messages, ThreadMessage(role="assistant", content=final_response.answer))
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
        prompt: list[ChatMessage] = [ChatMessage(role="system", content="\n".join(parts))]
        for message in state.active_messages[-self._settings.recent_messages :]:
            prompt.append(ChatMessage(role=message.role, content=message.content))
        return _parse_chat_response(self._llm.complete(prompt))

    def _build_follow_up_prompt(self, state: ThreadState, tool_result: str) -> list[ChatMessage]:
        """Build a prompt for the follow-up after tool invocation."""
        follow_up_system = (
            "You are NuSelf. The previous tool call returned the following results. "
            "Use these results to generate your final answer. "
            "Return a JSON object with answer, evidence_references, confidence, and epistemic_status."
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

        parts.extend([
            "",
            "Available tools:",
            'You may invoke a tool by including a "tool" field in your JSON:',
            '{"answer": "...", "tool": "search_memory", "tool_args": {"query": "search term"}, ...}',
            'The tool result will be injected back into context before your final answer.',
            'Tools available:',
            (
                "- search_memory(query: str, limit: int = 8, types: list[str] = [], tags: list[str] = []): "
                "Search durable memory for relevant context, optionally narrowed by memory type or tag."
            ),
            (
                "- list_pending_reflections(limit: int = 5): "
                "View pending proactive ideas generated from the user's memory and conversations. "
                "Use when the user seems open to exploring new topics or when the conversation naturally pauses."
            ),
            (
                "- dismiss_reflection(index: int): "
                "Remove a pending idea from the active pool when the user explicitly declines interest. "
                "Index corresponds to the numbered list from list_pending_reflections."
            ),
            (
                "- archive_reflection(index: int): "
                "Archive a pending reflection idea after the discussion is complete. "
                "Use when the user has engaged with a reflection and the topic feels resolved. "
                "Index corresponds to the numbered list from list_pending_reflections."
            ),
            (
                "- archive_memory(entry_id: str): "
                "Archive a memory entry so it is excluded from default search. "
                "Use when the user says a memory is outdated or no longer relevant."
            ),
            (
                "- update_memory_importance(entry_id: str, importance: float): "
                "Adjust the importance score (0.0–1.0) of a memory entry. "
                "Use when the user emphasizes or downplays the significance of a memory."
            ),
            "",
            "Behavioral guidelines:",
            "- When the user is in a casual or open-ended mood, or when the conversation naturally pauses, you may call list_pending_reflections to discover topics worth discussing.",
            "- If a reflection topic resonates with the user, discuss it naturally in your own words. Do not dump the raw list.",
            "- If the user shows no interest in a suggested topic, call dismiss_reflection.",
            "- If the user engages with a reflection and the discussion feels complete, call archive_reflection. The conversation itself captures the outcome into memory.",
            "- You can also help curate memory: archive outdated entries or adjust importance when the user signals relevance changes.",
        ])
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

        try:
            tool_obj = self._tools[tool.tool]
            # Tool invoke handles type conversion internally
            return tool_obj.invoke(**tool_args_input)
        except TypeError as e:
            return f"Error invoking {tool.tool}: {e}"
        except Exception as e:
            return f"Error: {e}"

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


@dataclass(frozen=True)
class ParsedChatResponse:
    answer: str
    evidence_references: tuple[str, ...] = ()
    confidence: float | None = None
    epistemic_status: str = "inferred"
    tool: str | None = None
    tool_args: dict[str, Any] | None = None


def _parse_chat_response(raw: str) -> ParsedChatResponse:
    stripped = raw.strip()
    if stripped.startswith("{"):
        try:
            parsed: object = json.loads(stripped)
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


def _apply_unsupported_claim_guard(response: ParsedChatResponse) -> ParsedChatResponse:
    if response.evidence_references:
        return response
    if not _looks_like_personal_claim(response.answer):
        return response
    confidence = response.confidence if response.confidence is not None else 0.25
    return ParsedChatResponse(
        answer=response.answer,
        evidence_references=response.evidence_references,
        confidence=min(confidence, 0.25),
        epistemic_status="unsupported",
        tool=response.tool,
        tool_args=response.tool_args,
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
