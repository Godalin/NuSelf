"""Memory-aware temporary chat agent."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import fcntl
import json
from pathlib import Path
from typing import Literal, TypeVar, cast

from nuself.config import config_int, runtime_paths
from nuself.llm import ChatLLM, ChatMessage, default_llm
from nuself.memory.query import MemoryQuery, MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository

ThreadRole = Literal["user", "assistant"]
UpdateResult = TypeVar("UpdateResult")


@dataclass(frozen=True)
class ChatAgentSettings:
    """Context window settings for the temporary chat agent."""

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
    """Temporary memory-aware chat agent with persisted context compression."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        llm: ChatLLM | None = None,
        settings: ChatAgentSettings | None = None,
        thread_store: ThreadStore | None = None,
        memory_query_service: MemoryQueryService | None = None,
    ) -> None:
        self._project_root = project_root
        self._llm = llm or default_llm(project_root)
        self._settings = settings or ChatAgentSettings.from_project(project_root)
        self._thread_store = thread_store or ThreadStore(project_root)
        self._memory_query_service = memory_query_service or MemoryQueryService(
            MemoryEntryRepository(project_root),
            SourceRepository(project_root),
            ProfileItemRepository(project_root),
        )

    def respond(self, message: str, thread_id: str = "default") -> ChatResult:
        def update(state: ThreadState) -> tuple[ThreadState, ChatResult]:
            base_messages = _drop_local_fallback_replies(state.messages)
            messages = [*base_messages, ThreadMessage(role="user", content=message)]
            prompt = self._build_prompt(
                ThreadState(thread_id=thread_id, summary=state.summary, messages=messages),
                message,
            )
            raw_reply = self._llm.complete(prompt)
            response = _apply_unsupported_claim_guard(_parse_chat_response(raw_reply))
            updated = ThreadState(
                thread_id=thread_id,
                summary=state.summary,
                messages=[*messages, ThreadMessage(role="assistant", content=response.answer)],
                message_start_index=state.message_start_index,
                next_message_index=state.next_message_index + 2,
            )
            compressed = self._compress_if_needed(updated)
            return compressed, ChatResult(
                answer=response.answer,
                thread_id=thread_id,
                evidence_references=response.evidence_references,
                confidence=response.confidence,
                epistemic_status=response.epistemic_status,
            )

        return self._thread_store.update(thread_id, update)

    def _build_prompt(self, state: ThreadState, user_message: str) -> list[ChatMessage]:
        prompt: list[ChatMessage] = [ChatMessage(role="system", content=self._system_prompt(user_message, state.summary))]
        for message in state.messages[-self._settings.recent_messages :]:
            prompt.append(ChatMessage(role=message.role, content=message.content))
        return prompt

    def _system_prompt(self, user_message: str, summary: str) -> str:
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
        packed_memory = self._memory_query_service.pack(MemoryQuery(text=user_message))
        if packed_memory.text != "":
            parts.extend(["", "Relevant memory context:", packed_memory.text])
        if summary != "":
            parts.extend(["", "Compressed conversation so far:", summary])
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


def _drop_local_fallback_replies(messages: list[ThreadMessage]) -> list[ThreadMessage]:
    return [message for message in messages if not _is_local_fallback_reply(message)]


def _is_local_fallback_reply(message: ThreadMessage) -> bool:
    return message.role == "assistant" and message.content.startswith("LLM API is not configured yet.")


@dataclass(frozen=True)
class ParsedChatResponse:
    answer: str
    evidence_references: tuple[str, ...] = ()
    confidence: float | None = None
    epistemic_status: str = "inferred"


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
            epistemic_status = _string_field(data.get("epistemic_status"), default="inferred")
            return ParsedChatResponse(
                answer=answer,
                evidence_references=evidence_references,
                confidence=confidence,
                epistemic_status=epistemic_status,
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


def _string_field(value: object, *, default: str) -> str:
    if isinstance(value, str) and value.strip() != "":
        return value
    return default
