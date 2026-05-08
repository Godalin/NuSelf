"""Memory-aware LangGraph-backed chat agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
import fcntl
import json
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar, cast

from nuself.agent.tools import MemorySearchTool
from nuself.agent.persona import (
    PersonaActivation,
    PersonaActivationPolicy,
    PersonaGraphDriver,
    PersonaInput,
    PersonaTurnState,
)
from nuself.config import config_int, runtime_paths, ensure_runtime_dirs
from nuself.llm import ChatLLM, ChatMessage, default_llm
from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository

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
        recent = config_int("NUSELF_CONTEXT_RECENT_MESSAGES", 12, project_root)
        trigger = config_int("NUSELF_CONTEXT_SUMMARY_TRIGGER_MESSAGES", 18, project_root)
        return cls(
            recent_messages=recent,
            summary_trigger_messages=max(trigger, recent + 2),
            summary_target_chars=config_int("NUSELF_CONTEXT_SUMMARY_TARGET_CHARS", 2400, project_root),
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
        self._persona_activation_policy = PersonaActivationPolicy()
        self._persona_driver = PersonaGraphDriver()
        self._memory_query_service = memory_query_service or MemoryQueryService(
            MemoryEntryRepository(project_root),
            SourceRepository(project_root),
            ProfileItemRepository(project_root),
        )
        self._tools: dict[str, MemorySearchTool] = {
            "search_memory": MemorySearchTool(query_service=self._memory_query_service)
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
        activation = self._persona_activation_policy.decide(
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
        # Render a compact persona summary for REPL/logs (private runtime only).
        try:
            summary = _compact_persona_summary(updated_persona_turn_state)
            paths = runtime_paths(self._project_root)
            ensure_runtime_dirs(paths)
            hist = paths.runtime_dir / "interactive_history"
            with hist.open("a", encoding="utf-8") as fh:
                fh.write("\n[PERSONA_SUMMARY] ")
                fh.write(summary)
                fh.write("\n")
        except Exception:
            # Do not let logging failures break the conversation runtime.
            pass
        return ConversationNodeResult(
            node="run_personas",
            state=replace(
                state,
                persona_turn_state=updated_persona_turn_state,
                node_trace=(*state.node_trace, "run_personas"),
            ),
        )

    def initial_response_node(self, state: ConversationTurnState) -> ConversationNodeResult:
        prompt = self._build_prompt(state)
        return ConversationNodeResult(
            node="initial_response",
            state=replace(
                state,
                initial_response=_parse_chat_response(self._llm.complete(prompt)),
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
        prompt: list[ChatMessage] = [ChatMessage(role="system", content=self._system_prompt(state))]
        for message in state.active_messages[-self._settings.recent_messages :]:
            prompt.append(ChatMessage(role=message.role, content=message.content))
        return prompt

    def _build_follow_up_prompt(self, state: ThreadState, tool_result: str) -> list[ChatMessage]:
        """Build a prompt for the follow-up after tool invocation."""
        prompt: list[ChatMessage] = [
            ChatMessage(
                role="system",
                content=(
                    "You are NuSelf. The previous tool call returned the following results. "
                    "Use these results to generate your final answer. "
                    "Return a JSON object with answer, evidence_references, confidence, and epistemic_status."
                ),
            )
        ]
        # Include recent message history
        for message in state.messages[-self._settings.recent_messages :]:
            prompt.append(ChatMessage(role=message.role, content=message.content))
        # Add tool result
        prompt.append(ChatMessage(role="user", content=f"Tool result:\n{tool_result}"))
        return prompt

    def _system_prompt(self, state: ConversationTurnState) -> str:
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
        if state.memory_context != "":
            parts.extend(["", "Relevant memory context:", state.memory_context])
        if state.persisted_state.summary != "":
            parts.extend(["", "Compressed conversation so far:", state.persisted_state.summary])
        parts.extend([
            "",
            "Available tools:",
            'If you need more specific memory context, you can use the search_memory tool by including a "tool" field in your JSON:',
            '{"answer": "...", "tool": "search_memory", "tool_args": {"query": "search term"}, ...}',
            'This will search all memory and return additional context before generating your final answer.',
            'Tools available:',
            (
                "- search_memory(query: str, limit: int = 8, types: list[str] = [], tags: list[str] = []): "
                "Search durable memory for relevant context, optionally narrowed by memory type or tag."
            ),
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
    if not parts:
        return "(no persona contributions)"
    return " | ".join(parts)


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
    return ParsedChatResponse(answer=raw)


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
    return None


def _string_field(value: object, *, default: str | None = None) -> str | None:
    if isinstance(value, str) and value.strip() != "":
        return value
    return default
