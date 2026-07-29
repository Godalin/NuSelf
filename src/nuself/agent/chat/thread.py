"""Thread state and persistence for chat conversations."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
import fcntl
import json
from pathlib import Path
from typing import Generator, Literal, TypeVar, cast

from nuself.config import runtime_paths
from nuself.private_fs import ensure_private_directory, ensure_private_file
from nuself.storage import write_json_atomic

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
        )


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
        ensure_private_directory(self._threads_dir)
        return _ThreadLock(self._lock_path_for(thread_id))

    @contextmanager
    def _locked_many(
        self,
        *thread_ids: str,
    ) -> Generator[None, None, None]:
        """Lock distinct logical threads in one deterministic order."""

        ordered = sorted(set(thread_ids))
        with ExitStack() as stack:
            for thread_id in ordered:
                stack.enter_context(self._locked(thread_id))
            yield

    def _load_unlocked(self, thread_id: str) -> ThreadState:
        path = self._path_for(thread_id)
        if not path.exists():
            return ThreadState.empty(thread_id)
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"thread file must contain an object: {path}")
        return ThreadState.from_wire(cast(dict[str, object], raw))

    def _save_unlocked(self, state: ThreadState) -> None:
        ensure_private_directory(self._threads_dir)
        path = self._path_for(state.thread_id)
        write_json_atomic(path, state.to_wire())

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
        """Rename one latest locked thread snapshot."""
        if old_thread_id == new_thread_id:
            return
        with self._locked_many(old_thread_id, new_thread_id):
            old_path = self._path_for(old_thread_id)
            new_path = self._path_for(new_thread_id)
            if not old_path.exists():
                raise ValueError(f"thread not found: {old_thread_id}")
            if new_path.exists():
                raise ValueError(
                    f"thread already exists: {new_thread_id}"
                )
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

    def branch(
        self,
        source_thread_id: str,
        new_thread_id: str,
        message_index: int | None = None,
    ) -> ThreadState:
        """Branch a new thread from a source thread up to a message index.

        If message_index is None, branches from the current end.
        """
        with self._locked_many(source_thread_id, new_thread_id):
            source_path = self._path_for(source_thread_id)
            new_path = self._path_for(new_thread_id)
            if not source_path.exists():
                raise ValueError(
                    f"source thread not found: {source_thread_id}"
                )
            if new_path.exists():
                raise ValueError(
                    f"thread already exists: {new_thread_id}"
                )
            source = self._load_unlocked(source_thread_id)
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
        """Move a thread file to the archived subdirectory."""
        with self._locked(thread_id):
            source_path = self._path_for(thread_id)
            if not source_path.exists():
                raise ValueError(f"thread not found: {thread_id}")
            archived_dir = self._threads_dir / "archived"
            ensure_private_directory(archived_dir)
            target_path = archived_dir / f"{thread_id}.json"
            if target_path.exists():
                raise ValueError(
                    f"archived thread already exists: {thread_id}"
                )
            source_path.rename(target_path)

    def unarchive(self, thread_id: str) -> None:
        """Move a thread file from the archived subdirectory back to active."""
        with self._locked(thread_id):
            archived_dir = self._threads_dir / "archived"
            source_path = archived_dir / f"{thread_id}.json"
            if not source_path.exists():
                raise ValueError(
                    f"archived thread not found: {thread_id}"
                )
            target_path = self._path_for(thread_id)
            if target_path.exists():
                raise ValueError(f"thread already exists: {thread_id}")
            source_path.rename(target_path)

    def delete(self, thread_id: str) -> None:
        """Permanently delete a thread while retaining its stable lock."""
        with self._locked(thread_id):
            path = self._path_for(thread_id)
            if not path.exists():
                raise ValueError(f"thread not found: {thread_id}")
            path.unlink()


class _ThreadLock:
    """Advisory file lock for one working-memory stream."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._file = None

    def __enter__(self) -> None:
        ensure_private_file(self._path)
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
