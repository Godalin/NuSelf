"""Conversation state and persistence for chat conversations."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field, replace
import fcntl
import hashlib
import time
from pathlib import Path
from typing import Generator, Literal, TypeVar, cast

from nuself.config import RuntimePaths
from nuself.private_fs import ensure_private_directory, ensure_private_file
from nuself.storage import StorageBackend

ConversationRole = Literal["user", "assistant"]
UpdateResult = TypeVar("UpdateResult")


class ConversationTurnConflictError(RuntimeError):
    """A stable turn ID was reused with different user input."""


class ConversationTurnIncompleteError(RuntimeError):
    """A prior execution of one stable turn did not commit a reply."""


@dataclass(frozen=True)
class _PendingTurn:
    """Payload-safe evidence that one stable turn began execution."""

    turn_id: str
    input_digest: str

    @classmethod
    def from_message(cls, turn_id: str, message: str) -> _PendingTurn:
        return cls(
            turn_id=turn_id,
            input_digest=hashlib.sha256(
                message.encode("utf-8")
            ).hexdigest(),
        )

    def to_wire(self) -> dict[str, str]:
        return {
            "turn_id": self.turn_id,
            "input_digest": self.input_digest,
        }

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> _PendingTurn:
        if set(data) != {"turn_id", "input_digest"}:
            raise ValueError("pending turn fields are invalid")
        turn_id = data["turn_id"]
        input_digest = data["input_digest"]
        if not isinstance(turn_id, str) or not turn_id:
            raise ValueError("pending turn ID must be a non-empty string")
        if (
            not isinstance(input_digest, str)
            or len(input_digest) != 64
            or any(char not in "0123456789abcdef" for char in input_digest)
        ):
            raise ValueError("pending turn input digest is invalid")
        return cls(turn_id=turn_id, input_digest=input_digest)


@dataclass(frozen=True)
class ConversationMessage:
    """A persisted user or assistant message in a NuSelf conversation."""

    role: ConversationRole
    content: str
    turn_id: str | None = None

    def to_wire(self) -> dict[str, str]:
        wire = {"role": self.role, "content": self.content}
        if self.turn_id is not None:
            wire["turn_id"] = self.turn_id
        return wire

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "ConversationMessage":
        unexpected = set(data) - {"role", "content", "turn_id"}
        if unexpected:
            raise ValueError("conversation message contains unsupported fields")
        role = data.get("role")
        content = data.get("content")
        turn_id = data.get("turn_id")
        if role not in {"user", "assistant"}:
            raise ValueError("conversation message role must be user or assistant")
        if not isinstance(content, str):
            raise ValueError("conversation message content must be a string")
        if turn_id is not None and not isinstance(turn_id, str):
            raise ValueError("conversation message turn_id must be a string when present")
        return cls(
            role=cast(ConversationRole, role),
            content=content,
            turn_id=turn_id,
        )


def empty_conversation_messages() -> list[ConversationMessage]:
    return []


@dataclass(frozen=True)
class ConversationState:
    """Persisted state for one conversation."""

    conversation_id: str
    summary: str = ""
    messages: list[ConversationMessage] = field(default_factory=empty_conversation_messages)
    message_start_index: int = 0
    next_message_index: int = 0
    archived: bool = False
    pending_turns: tuple[_PendingTurn, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.next_message_index == self.message_start_index and self.messages:
            object.__setattr__(self, "next_message_index", self.message_start_index + len(self.messages))
        self._validate_indexes()
        pending_ids = [item.turn_id for item in self.pending_turns]
        if len(pending_ids) != len(set(pending_ids)):
            raise ValueError("pending turn IDs must be unique")

    def to_wire(self) -> dict[str, object]:
        self._validate_indexes()
        wire: dict[str, object] = {
            "conversation_id": self.conversation_id,
            "summary": self.summary,
            "messages": [message.to_wire() for message in self.messages],
            "message_start_index": self.message_start_index,
            "next_message_index": self.next_message_index,
            "archived": self.archived,
        }
        if self.pending_turns:
            wire["pending_turns"] = [
                pending.to_wire() for pending in self.pending_turns
            ]
        return wire

    def _validate_indexes(self) -> None:
        if (
            type(self.message_start_index) is not int
            or self.message_start_index < 0
        ):
            raise ValueError(
                "message_start_index must be a non-negative integer"
            )
        if (
            type(self.next_message_index) is not int
            or self.next_message_index < 0
        ):
            raise ValueError(
                "next_message_index must be a non-negative integer"
            )
        if self.next_message_index != self.message_start_index + len(self.messages):
            raise ValueError(
                "next_message_index must equal message_start_index plus "
                "the message count"
            )

    @classmethod
    def empty(cls, conversation_id: str) -> "ConversationState":
        return cls(conversation_id=conversation_id)

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "ConversationState":
        conversation_id = data.get("conversation_id")
        summary = data.get("summary")
        messages = data.get("messages")
        message_start_index = data.get("message_start_index", 0)
        next_message_index = data.get("next_message_index")
        archived = data.get("archived", False)
        pending_turns = data.get("pending_turns", [])
        if not isinstance(conversation_id, str):
            raise ValueError("conversation_id must be a string")
        if not isinstance(summary, str):
            raise ValueError("summary must be a string")
        if not isinstance(messages, list):
            raise ValueError("messages must be a list")
        if type(message_start_index) is not int or message_start_index < 0:
            raise ValueError("message_start_index must be a non-negative integer")
        message_items = cast(list[object], messages)
        if any(not isinstance(item, dict) for item in message_items):
            raise ValueError("every conversation message must be an object")
        parsed_messages = [
            ConversationMessage.from_wire(cast(dict[str, object], item))
            for item in message_items
        ]
        if next_message_index is None:
            next_message_index = message_start_index + len(parsed_messages)
        if type(next_message_index) is not int or next_message_index < 0:
            raise ValueError("next_message_index must be a non-negative integer")
        if not isinstance(archived, bool):
            raise ValueError("archived must be a boolean")
        if not isinstance(pending_turns, list):
            raise ValueError("pending_turns must be an object list")
        pending_items = cast(list[object], pending_turns)
        if any(not isinstance(item, dict) for item in pending_items):
            raise ValueError("pending_turns must be an object list")
        decoded_pending = tuple(
            _PendingTurn.from_wire(cast(dict[str, object], item))
            for item in pending_items
        )
        pending_ids = [item.turn_id for item in decoded_pending]
        if len(pending_ids) != len(set(pending_ids)):
            raise ValueError("pending turn IDs must be unique")
        expected_next_index = message_start_index + len(parsed_messages)
        if next_message_index != expected_next_index:
            raise ValueError(
                "next_message_index must equal message_start_index plus "
                "the message count"
            )
        return cls(
            conversation_id=conversation_id,
            summary=summary,
            messages=parsed_messages,
            message_start_index=message_start_index,
            next_message_index=next_message_index,
            archived=archived,
            pending_turns=decoded_pending,
        )


class ConversationStore:
    """SQLite-backed conversation store under the selected authority."""

    def __init__(
        self,
        paths: RuntimePaths,
        *,
        backend: StorageBackend,
    ) -> None:
        self._locks_dir = paths.runtime_dir / "conversation-locks"
        self._backend = backend
        self._collection = self._backend.collection("conversations")

    def load(self, conversation_id: str) -> ConversationState:
        self._validate_id(conversation_id)
        return self._load_unlocked(conversation_id)

    def save(self, state: ConversationState) -> None:
        self._validate_id(state.conversation_id)
        with self._locked(state.conversation_id), self._backend.transaction():
            self._save_unlocked(state)

    def update(
        self,
        conversation_id: str,
        update: Callable[[ConversationState], tuple[ConversationState, UpdateResult]],
        *,
        turn_id: str | None = None,
        user_message: str | None = None,
        commit_observer: Callable[[int], None] | None = None,
    ) -> UpdateResult:
        """Serialize one turn without holding SQLite across model execution."""

        self._validate_id(conversation_id)
        if (turn_id is None) != (user_message is None):
            raise ValueError(
                "turn_id and user_message must be supplied together"
            )
        with self._locked(conversation_id):
            original = self._collection.get(conversation_id)
            state = (
                ConversationState.empty(conversation_id)
                if original is None
                else ConversationState.from_wire(original)
            )
            if turn_id is not None and not any(
                item.turn_id == turn_id and item.role == "assistant"
                for item in state.messages
            ):
                assert user_message is not None
                state = _begin_turn_attempt(
                    state,
                    turn_id,
                    user_message,
                )
                with self._backend.transaction():
                    self._save_unlocked(state)
                original = self._collection.get(conversation_id)
            updated, result = update(state)
            if updated.conversation_id != conversation_id:
                raise ValueError("conversation update cannot change conversation identity")
            commit_started_at = time.monotonic()
            with self._backend.transaction():
                if self._collection.get(conversation_id) != original:
                    raise ValueError(
                        "conversation changed concurrently; retry the turn"
                    )
                self._save_unlocked(
                    _finish_turn_attempt(updated, turn_id)
                )
            if commit_observer is not None:
                commit_observer(
                    int((time.monotonic() - commit_started_at) * 1000)
                )
            return result

    def _load_unlocked(self, conversation_id: str) -> ConversationState:
        raw = self._collection.get(conversation_id)
        if raw is None:
            return ConversationState.empty(conversation_id)
        return ConversationState.from_wire(raw)

    def _save_unlocked(self, state: ConversationState) -> None:
        self._collection.put(state.conversation_id, state.to_wire())

    def _locked(self, conversation_id: str) -> "_ConversationLock":
        self._validate_id(conversation_id)
        ensure_private_directory(self._locks_dir)
        return _ConversationLock(self._locks_dir / f"{conversation_id}.lock")

    @contextmanager
    def _locked_many(
        self,
        *conversation_ids: str,
    ) -> Generator[None, None, None]:
        with ExitStack() as stack:
            for conversation_id in sorted(set(conversation_ids)):
                stack.enter_context(self._locked(conversation_id))
            yield

    @staticmethod
    def _validate_id(conversation_id: str) -> None:
        if (
            conversation_id == ""
            or "/" in conversation_id
            or "\\" in conversation_id
            or conversation_id in {".", ".."}
        ):
            raise ValueError(f"invalid conversation id: {conversation_id}")

    def list(self) -> list[str]:
        """List persisted conversation IDs, excluding archived conversations."""
        return sorted(
            state.conversation_id
            for state in self._states()
            if not state.archived
        )

    def list_archived(self) -> list[str]:
        """List archived conversation IDs."""
        return sorted(
            state.conversation_id
            for state in self._states()
            if state.archived
        )

    def _states(self) -> tuple[ConversationState, ...]:
        return tuple(
            ConversationState.from_wire(item)
            for item in self._collection.list()
        )

    def rename(self, old_conversation_id: str, new_conversation_id: str) -> None:
        """Rename one latest locked conversation snapshot."""
        if old_conversation_id == new_conversation_id:
            return
        self._validate_id(old_conversation_id)
        self._validate_id(new_conversation_id)
        with self._locked_many(old_conversation_id, new_conversation_id), self._backend.transaction():
            raw = self._collection.get(old_conversation_id)
            if raw is None:
                raise ValueError(f"conversation not found: {old_conversation_id}")
            if self._collection.get(new_conversation_id) is not None:
                raise ValueError(
                    f"conversation already exists: {new_conversation_id}"
                )
            state = ConversationState.from_wire(raw)
            renamed = replace(state, conversation_id=new_conversation_id)
            self._save_unlocked(renamed)
            self._collection.delete(old_conversation_id)

    def branch(
        self,
        source_conversation_id: str,
        new_conversation_id: str,
        message_index: int | None = None,
    ) -> ConversationState:
        """Branch a new conversation from a source up to a message index.

        If message_index is None, branches from the current end.
        """
        self._validate_id(source_conversation_id)
        self._validate_id(new_conversation_id)
        with self._locked_many(source_conversation_id, new_conversation_id), self._backend.transaction():
            source_raw = self._collection.get(source_conversation_id)
            if source_raw is None:
                raise ValueError(
                    f"source conversation not found: {source_conversation_id}"
                )
            if self._collection.get(new_conversation_id) is not None:
                raise ValueError(
                    f"conversation already exists: {new_conversation_id}"
                )
            source = ConversationState.from_wire(source_raw)
            branch_index = (
                len(source.messages)
                if message_index is None
                else message_index
            )
            if (
                branch_index < 0
                or branch_index > len(source.messages)
            ):
                raise ValueError(
                    f"branch index {branch_index} out of range "
                    f"(0..{len(source.messages)})"
                )
            branched = ConversationState(
                conversation_id=new_conversation_id,
                summary=source.summary,
                messages=source.messages[:branch_index],
                message_start_index=source.message_start_index,
                next_message_index=(
                    source.message_start_index + branch_index
                ),
                pending_turns=(),
            )
            self._save_unlocked(branched)
            return branched

    def archive(self, conversation_id: str) -> None:
        """Mark a conversation as archived."""
        self._validate_id(conversation_id)
        with self._locked(conversation_id), self._backend.transaction():
            raw = self._collection.get(conversation_id)
            if raw is None:
                raise ValueError(f"conversation not found: {conversation_id}")
            state = ConversationState.from_wire(raw)
            if state.archived:
                raise ValueError(
                    f"archived conversation already exists: {conversation_id}"
                )
            self._save_unlocked(_with_archived(state, True))

    def unarchive(self, conversation_id: str) -> None:
        """Restore an archived conversation."""
        self._validate_id(conversation_id)
        with self._locked(conversation_id), self._backend.transaction():
            raw = self._collection.get(conversation_id)
            if raw is None:
                raise ValueError(
                    f"archived conversation not found: {conversation_id}"
                )
            state = ConversationState.from_wire(raw)
            if not state.archived:
                raise ValueError(f"conversation already exists: {conversation_id}")
            self._save_unlocked(_with_archived(state, False))

    def delete(self, conversation_id: str) -> None:
        """Permanently delete a conversation."""
        self._validate_id(conversation_id)
        with self._locked(conversation_id), self._backend.transaction():
            if self._collection.get(conversation_id) is None:
                raise ValueError(f"conversation not found: {conversation_id}")
            self._collection.delete(conversation_id)

    def recent_context(
        self,
        max_conversations: int,
        max_messages: int,
    ) -> str:
        """Render bounded model context for cross-domain consumers."""

        lines: list[str] = []
        for conversation_id in reversed(
            self.list()[-max_conversations:]
        ):
            state = self.load(conversation_id)
            lines.append(f"Conversation {conversation_id}:")
            lines.extend(
                f"  {message.role}: {message.content[:120]}"
                for message in state.messages[-max_messages:]
            )
        return "\n".join(lines)


def _with_archived(state: ConversationState, archived: bool) -> ConversationState:
    return replace(state, archived=archived)


def _begin_turn_attempt(
    state: ConversationState,
    turn_id: str,
    message: str,
) -> ConversationState:
    attempted = _PendingTurn.from_message(turn_id, message)
    for pending in state.pending_turns:
        if pending.turn_id != turn_id:
            continue
        if pending.input_digest != attempted.input_digest:
            raise ConversationTurnConflictError(
                f"turn ID {turn_id!r} is already bound to different input"
            )
        raise ConversationTurnIncompleteError(
            f"turn ID {turn_id!r} has an unfinished prior execution"
        )
    return replace(
        state,
        pending_turns=(*state.pending_turns, attempted),
    )


def _finish_turn_attempt(
    state: ConversationState,
    turn_id: str | None,
) -> ConversationState:
    if turn_id is None:
        return state
    return replace(
        state,
        pending_turns=tuple(
            pending
            for pending in state.pending_turns
            if pending.turn_id != turn_id
        ),
    )


class _ConversationLock:
    """Stable advisory lock for one working-memory stream."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file = None

    def __enter__(self) -> None:
        ensure_private_file(self._path)
        self._file = self._path.open("ab")
        fcntl.flock(self._file.fileno(), fcntl.LOCK_EX)

    def __exit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        if self._file is None:
            return
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None
