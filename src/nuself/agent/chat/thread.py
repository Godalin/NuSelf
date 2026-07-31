"""Thread state and persistence for chat conversations."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
import fcntl
from pathlib import Path
from typing import Generator, Literal, TypeVar, cast

from nuself.config import runtime_paths
from nuself.private_fs import ensure_private_directory, ensure_private_file
from nuself.storage import StorageBackend, get_default_backend

ThreadRole = Literal["user", "assistant"]
UpdateResult = TypeVar("UpdateResult")


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
        unexpected = set(data) - {"role", "content", "turn_id"}
        if unexpected:
            raise ValueError("thread message contains unsupported fields")
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
    archived: bool = False

    def __post_init__(self) -> None:
        if self.next_message_index == self.message_start_index and self.messages:
            object.__setattr__(self, "next_message_index", self.message_start_index + len(self.messages))
        self._validate_indexes()

    def to_wire(self) -> dict[str, object]:
        self._validate_indexes()
        return {
            "thread_id": self.thread_id,
            "summary": self.summary,
            "messages": [message.to_wire() for message in self.messages],
            "message_start_index": self.message_start_index,
            "next_message_index": self.next_message_index,
            "archived": self.archived,
        }

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
    def empty(cls, thread_id: str) -> "ThreadState":
        return cls(thread_id=thread_id)

    @classmethod
    def from_wire(cls, data: dict[str, object]) -> "ThreadState":
        thread_id = data.get("thread_id")
        summary = data.get("summary")
        messages = data.get("messages")
        message_start_index = data.get("message_start_index", 0)
        next_message_index = data.get("next_message_index")
        archived = data.get("archived", False)
        if not isinstance(thread_id, str):
            raise ValueError("thread_id must be a string")
        if not isinstance(summary, str):
            raise ValueError("summary must be a string")
        if not isinstance(messages, list):
            raise ValueError("messages must be a list")
        if type(message_start_index) is not int or message_start_index < 0:
            raise ValueError("message_start_index must be a non-negative integer")
        message_items = cast(list[object], messages)
        if any(not isinstance(item, dict) for item in message_items):
            raise ValueError("every thread message must be an object")
        parsed_messages = [
            ThreadMessage.from_wire(cast(dict[str, object], item))
            for item in message_items
        ]
        if next_message_index is None:
            next_message_index = message_start_index + len(parsed_messages)
        if type(next_message_index) is not int or next_message_index < 0:
            raise ValueError("next_message_index must be a non-negative integer")
        if not isinstance(archived, bool):
            raise ValueError("archived must be a boolean")
        expected_next_index = message_start_index + len(parsed_messages)
        if next_message_index != expected_next_index:
            raise ValueError(
                "next_message_index must equal message_start_index plus "
                "the message count"
            )
        return cls(
            thread_id=thread_id,
            summary=summary,
            messages=parsed_messages,
            message_start_index=message_start_index,
            next_message_index=next_message_index,
            archived=archived,
        )


class ThreadStore:
    """SQLite-backed chat thread store under the selected authority."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        backend: StorageBackend | None = None,
    ) -> None:
        self._locks_dir = runtime_paths(project_root).runtime_dir / "thread-locks"
        self._backend = (
            backend
            if backend is not None
            else get_default_backend(project_root)
        )
        self._collection = self._backend.collection("chat_threads")

    def load(self, thread_id: str) -> ThreadState:
        self._validate_id(thread_id)
        return self._load_unlocked(thread_id)

    def save(self, state: ThreadState) -> None:
        self._validate_id(state.thread_id)
        with self._locked(state.thread_id), self._backend.transaction():
            self._save_unlocked(state)

    def update(
        self,
        thread_id: str,
        update: Callable[[ThreadState], tuple[ThreadState, UpdateResult]],
    ) -> UpdateResult:
        """Serialize one turn without holding SQLite across model execution."""

        self._validate_id(thread_id)
        with self._locked(thread_id):
            original = self._collection.get(thread_id)
            state = (
                ThreadState.empty(thread_id)
                if original is None
                else ThreadState.from_wire(original)
            )
            updated, result = update(state)
            if updated.thread_id != thread_id:
                raise ValueError("thread update cannot change thread identity")
            with self._backend.transaction():
                if self._collection.get(thread_id) != original:
                    raise ValueError(
                        "thread changed concurrently; retry the turn"
                    )
                self._save_unlocked(updated)
            return result

    def _load_unlocked(self, thread_id: str) -> ThreadState:
        raw = self._collection.get(thread_id)
        if raw is None:
            return ThreadState.empty(thread_id)
        return ThreadState.from_wire(raw)

    def _save_unlocked(self, state: ThreadState) -> None:
        self._collection.put(state.thread_id, state.to_wire())

    def _locked(self, thread_id: str) -> "_ThreadLock":
        self._validate_id(thread_id)
        ensure_private_directory(self._locks_dir)
        return _ThreadLock(self._locks_dir / f"{thread_id}.lock")

    @contextmanager
    def _locked_many(
        self,
        *thread_ids: str,
    ) -> Generator[None, None, None]:
        with ExitStack() as stack:
            for thread_id in sorted(set(thread_ids)):
                stack.enter_context(self._locked(thread_id))
            yield

    @staticmethod
    def _validate_id(thread_id: str) -> None:
        if (
            thread_id == ""
            or "/" in thread_id
            or "\\" in thread_id
            or thread_id in {".", ".."}
        ):
            raise ValueError(f"invalid thread id: {thread_id}")

    def list(self) -> list[str]:
        """List persisted thread IDs, excluding archived threads."""
        return sorted(
            state.thread_id
            for state in self._states()
            if not state.archived
        )

    def list_archived(self) -> list[str]:
        """List archived thread IDs."""
        return sorted(
            state.thread_id
            for state in self._states()
            if state.archived
        )

    def _states(self) -> tuple[ThreadState, ...]:
        return tuple(
            ThreadState.from_wire(item)
            for item in self._collection.list()
        )

    def rename(self, old_thread_id: str, new_thread_id: str) -> None:
        """Rename one latest locked thread snapshot."""
        if old_thread_id == new_thread_id:
            return
        self._validate_id(old_thread_id)
        self._validate_id(new_thread_id)
        with self._locked_many(old_thread_id, new_thread_id), self._backend.transaction():
            raw = self._collection.get(old_thread_id)
            if raw is None:
                raise ValueError(f"thread not found: {old_thread_id}")
            if self._collection.get(new_thread_id) is not None:
                raise ValueError(
                    f"thread already exists: {new_thread_id}"
                )
            state = ThreadState.from_wire(raw)
            renamed = ThreadState(
                thread_id=new_thread_id,
                summary=state.summary,
                messages=state.messages,
                message_start_index=state.message_start_index,
                next_message_index=state.next_message_index,
                archived=state.archived,
            )
            self._save_unlocked(renamed)
            self._collection.delete(old_thread_id)

    def branch(
        self,
        source_thread_id: str,
        new_thread_id: str,
        message_index: int | None = None,
    ) -> ThreadState:
        """Branch a new thread from a source thread up to a message index.

        If message_index is None, branches from the current end.
        """
        self._validate_id(source_thread_id)
        self._validate_id(new_thread_id)
        with self._locked_many(source_thread_id, new_thread_id), self._backend.transaction():
            source_raw = self._collection.get(source_thread_id)
            if source_raw is None:
                raise ValueError(
                    f"source thread not found: {source_thread_id}"
                )
            if self._collection.get(new_thread_id) is not None:
                raise ValueError(
                    f"thread already exists: {new_thread_id}"
                )
            source = ThreadState.from_wire(source_raw)
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
            branched = ThreadState(
                thread_id=new_thread_id,
                summary=source.summary,
                messages=source.messages[:branch_index],
                message_start_index=source.message_start_index,
                next_message_index=(
                    source.message_start_index + branch_index
                ),
            )
            self._save_unlocked(branched)
            return branched

    def archive(self, thread_id: str) -> None:
        """Mark a thread as archived."""
        self._validate_id(thread_id)
        with self._locked(thread_id), self._backend.transaction():
            raw = self._collection.get(thread_id)
            if raw is None:
                raise ValueError(f"thread not found: {thread_id}")
            state = ThreadState.from_wire(raw)
            if state.archived:
                raise ValueError(
                    f"archived thread already exists: {thread_id}"
                )
            self._save_unlocked(_with_archived(state, True))

    def unarchive(self, thread_id: str) -> None:
        """Restore an archived thread."""
        self._validate_id(thread_id)
        with self._locked(thread_id), self._backend.transaction():
            raw = self._collection.get(thread_id)
            if raw is None:
                raise ValueError(
                    f"archived thread not found: {thread_id}"
                )
            state = ThreadState.from_wire(raw)
            if not state.archived:
                raise ValueError(f"thread already exists: {thread_id}")
            self._save_unlocked(_with_archived(state, False))

    def delete(self, thread_id: str) -> None:
        """Permanently delete a thread."""
        self._validate_id(thread_id)
        with self._locked(thread_id), self._backend.transaction():
            if self._collection.get(thread_id) is None:
                raise ValueError(f"thread not found: {thread_id}")
            self._collection.delete(thread_id)

    def recent_context(
        self,
        max_threads: int,
        max_messages: int,
    ) -> str:
        """Render bounded model context for cross-domain consumers."""

        lines: list[str] = []
        for thread_id in reversed(self.list()[-max_threads:]):
            state = self.load(thread_id)
            lines.append(f"Thread {thread_id}:")
            lines.extend(
                f"  {message.role}: {message.content[:120]}"
                for message in state.messages[-max_messages:]
            )
        return "\n".join(lines)


def _with_archived(state: ThreadState, archived: bool) -> ThreadState:
    return ThreadState(
        thread_id=state.thread_id,
        summary=state.summary,
        messages=state.messages,
        message_start_index=state.message_start_index,
        next_message_index=state.next_message_index,
        archived=archived,
    )


class _ThreadLock:
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
