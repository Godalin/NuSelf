"""Typed durable recovery plans for memory curation."""

from __future__ import annotations

from dataclasses import dataclass
from fcntl import LOCK_EX, LOCK_NB, LOCK_UN, flock
from pathlib import Path
from typing import IO, Literal, Never, cast
from uuid import NAMESPACE_URL, uuid5

from nuself.config import RuntimePaths
from nuself.domain.memory import (
    MemoryTypeRegistry,
    default_memory_type_registry,
)
from nuself.memory.curator_contract import (
    CuratorActionItem,
    MemoryAction,
    action_from_item,
)
from nuself.private_fs import ensure_private_file
from nuself.runtime.observability import report_corrupt_record
from nuself.storage import StorageBackend


@dataclass(frozen=True)
class MemoryCuratorPlan:
    """One durable structured decision awaiting cursor completion."""

    conversation_id: str
    source_start: int
    source_end: int
    observed_at: str
    actions: tuple[MemoryAction, ...]

    @property
    def source_ref(self) -> str:
        return (
            f"conversation:{self.conversation_id}:{self.source_start}-{self.source_end}"
        )

    def candidate_id(self, action_index: int) -> str:
        if action_index < 0 or action_index >= len(self.actions):
            raise IndexError("curator plan action index is out of range")
        return (
            f"cand_{uuid5(NAMESPACE_URL, f'{self.source_ref}:{action_index}').hex}"
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "conversation_id": self.conversation_id,
            "source_start": self.source_start,
            "source_end": self.source_end,
            "observed_at": self.observed_at,
            "actions": [
                {
                    "action": action.action,
                    "title": action.title,
                    "body": action.body,
                    "type": action.type,
                    "tags": list(action.tags),
                    "entry_id": action.entry_id,
                    "confidence": action.confidence,
                    "reason": action.reason,
                }
                for action in self.actions
            ],
        }

    @classmethod
    def from_wire(
        cls,
        data: dict[str, object],
        *,
        expected_conversation_id: str,
        allowed_types: tuple[str, ...],
    ) -> MemoryCuratorPlan:
        expected_fields = {
            "conversation_id",
            "source_start",
            "source_end",
            "observed_at",
            "actions",
        }
        if set(data) != expected_fields:
            raise ValueError("curator plan fields differ from schema")
        conversation_id = data["conversation_id"]
        if conversation_id != expected_conversation_id:
            raise ValueError("curator plan conversation identity mismatch")
        source_start = data["source_start"]
        source_end = data["source_end"]
        observed_at = data["observed_at"]
        if (
            isinstance(source_start, bool)
            or not isinstance(source_start, int)
            or isinstance(source_end, bool)
            or not isinstance(source_end, int)
            or source_start < 0
            or source_end <= source_start
        ):
            raise ValueError("curator plan source range is invalid")
        if not isinstance(observed_at, str) or observed_at == "":
            raise ValueError("curator plan observed_at is invalid")
        raw_actions = data["actions"]
        if not isinstance(raw_actions, list) or not raw_actions:
            raise ValueError(
                "curator plan actions must be a non-empty list"
            )
        action_values = cast(list[object], raw_actions)
        actions = tuple(
            action_from_item(
                CuratorActionItem.model_validate(raw_action),
                allowed_types=allowed_types,
            )
            for raw_action in action_values
        )
        return cls(
            conversation_id=expected_conversation_id,
            source_start=source_start,
            source_end=source_end,
            observed_at=observed_at,
            actions=actions,
        )


class MemoryCuratorPlanNotFound(KeyError):
    """Raised when one conversation has no curator recovery plan."""


class MemoryCuratorPlanCorruptError(ValueError):
    """Raised when a curator recovery plan cannot be trusted."""


class MemoryCuratorPlanLockContended(RuntimeError):
    """Raised when another process is mutating one conversation's curator state."""


class MemoryCuratorPlanLockCleanupError(RuntimeError):
    """A curator lock operation and required handle close both failed."""

    def __init__(
        self,
        operation: Literal["acquire", "release"],
        *,
        primary_error: BaseException,
        cleanup_error: BaseException,
    ) -> None:
        super().__init__(
            f"memory curator plan lock {operation} and handle cleanup "
            "both failed"
        )
        self.operation = operation
        self.primary_error = primary_error
        self.cleanup_error = cleanup_error


class MemoryCuratorPlanLock:
    """Hold one stable non-blocking advisory lock for curator mutation."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle: IO[str] | None = None

    @property
    def acquired(self) -> bool:
        return self._handle is not None

    def acquire(self) -> None:
        if self._handle is not None:
            return
        ensure_private_file(self.path)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            flock(handle.fileno(), LOCK_EX | LOCK_NB)
        except BlockingIOError:
            primary_error = MemoryCuratorPlanLockContended(
                "another process is mutating this conversation's curator state"
            )
            try:
                handle.close()
            except BaseException as cleanup_error:
                raise MemoryCuratorPlanLockCleanupError(
                    "acquire",
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
            raise primary_error from None
        except BaseException as primary_error:
            try:
                handle.close()
            except BaseException as cleanup_error:
                raise MemoryCuratorPlanLockCleanupError(
                    "acquire",
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
            raise
        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            flock(handle.fileno(), LOCK_UN)
        except BaseException as primary_error:
            try:
                handle.close()
            except BaseException as cleanup_error:
                raise MemoryCuratorPlanLockCleanupError(
                    "release",
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
            raise
        else:
            handle.close()

    def __enter__(self) -> MemoryCuratorPlanLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object,
    ) -> None:
        self.release()


class MemoryCuratorPlanStore:
    """Typed cursor-adjacent storage for curator recovery plans."""

    def __init__(
        self,
        paths: RuntimePaths,
        backend: StorageBackend,
        *,
        registry: MemoryTypeRegistry | None = None,
    ) -> None:
        self._paths = paths
        self._registry = registry or default_memory_type_registry()
        self._backend = backend
        self._collection = self._backend.collection(
            "memory_curator_plans"
        )

    def get(self, conversation_id: str) -> MemoryCuratorPlan | None:
        try:
            raw = self._collection.get(conversation_id)
            if raw is None:
                return None
            return MemoryCuratorPlan.from_wire(
                _without_storage_id(raw),
                expected_conversation_id=conversation_id,
                allowed_types=self._registry.names(),
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            self._raise_corrupt(conversation_id, exc)

    def resumable(
        self,
        conversation_id: str,
        *,
        cursor: int,
        next_message_index: int,
    ) -> MemoryCuratorPlan | None:
        try:
            raw = self._collection.get(conversation_id)
            if raw is None:
                return None
            raw_mapping = _without_storage_id(raw)
            stored_conversation_id = raw_mapping.get("conversation_id")
            stored_source_end = raw_mapping.get("source_end")
            if (
                stored_conversation_id == conversation_id
                and not isinstance(stored_source_end, bool)
                and isinstance(stored_source_end, int)
                and stored_source_end <= cursor
            ):
                return None
            plan = MemoryCuratorPlan.from_wire(
                raw_mapping,
                expected_conversation_id=conversation_id,
                allowed_types=self._registry.names(),
            )
            if plan.source_start != cursor:
                raise ValueError(
                    "curator plan does not start at the durable cursor"
                )
            if plan.source_end > next_message_index:
                raise ValueError(
                    "curator plan extends beyond the current conversation"
                )
            return plan
        except (
            TypeError,
            ValueError,
        ) as exc:
            self._raise_corrupt(conversation_id, exc)

    def save(self, plan: MemoryCuratorPlan) -> MemoryCuratorPlan:
        self._collection.put(plan.conversation_id, plan.to_wire())
        return plan

    def discard(self, conversation_id: str) -> None:
        with self.exclusive(conversation_id):
            with self._backend.transaction():
                if self._collection.get(conversation_id) is None:
                    raise MemoryCuratorPlanNotFound(conversation_id)
                self._collection.delete(conversation_id)

    def exclusive(self, conversation_id: str) -> MemoryCuratorPlanLock:
        """Return the authoritative mutation lock for one curator conversation."""

        validate_curator_conversation_id(conversation_id)
        return MemoryCuratorPlanLock(
            self._paths.runtime_dir
            / "curator-locks"
            / f"{conversation_id}.lock"
        )

    def _raise_corrupt(
        self,
        conversation_id: str,
        exc: Exception,
    ) -> Never:
        report_corrupt_record(
            exc,
            component="memory",
            collection="memory_curator_plans",
            record_id=conversation_id,
            project_root=self._paths.project_root,
        )
        raise MemoryCuratorPlanCorruptError(
            f"invalid memory curator plan for conversation {conversation_id!r}; "
            "inspect with 'nuself memory plan show CONVERSATION' or explicitly "
            "discard with 'nuself memory plan discard CONVERSATION --force'"
        ) from exc


def validate_curator_conversation_id(conversation_id: str) -> None:
    if conversation_id == "" or "/" in conversation_id or conversation_id in {".", ".."}:
        raise ValueError(f"invalid conversation id: {conversation_id}")


def _without_storage_id(
    record: dict[str, object],
) -> dict[str, object]:
    return {key: value for key, value in record.items() if key != "id"}
