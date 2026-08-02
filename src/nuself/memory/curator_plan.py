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
    """One durable structured decision awaiting observation completion."""

    observation_id: str
    source_ref: str
    observed_at: str
    actions: tuple[MemoryAction, ...]

    def candidate_id(self, action_index: int) -> str:
        if action_index < 0 or action_index >= len(self.actions):
            raise IndexError("curator plan action index is out of range")
        return (
            f"cand_{uuid5(NAMESPACE_URL, f'{self.source_ref}:{action_index}').hex}"
        )

    def to_wire(self) -> dict[str, object]:
        return {
            "observation_id": self.observation_id,
            "source_ref": self.source_ref,
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
        expected_observation_id: str,
        allowed_types: tuple[str, ...],
    ) -> MemoryCuratorPlan:
        expected_fields = {
            "observation_id",
            "source_ref",
            "observed_at",
            "actions",
        }
        if set(data) != expected_fields:
            raise ValueError("curator plan fields differ from schema")
        observation_id = data["observation_id"]
        if observation_id != expected_observation_id:
            raise ValueError("curator plan observation identity mismatch")
        source_ref = data["source_ref"]
        observed_at = data["observed_at"]
        if not isinstance(source_ref, str) or source_ref == "":
            raise ValueError("curator plan source reference is invalid")
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
            observation_id=expected_observation_id,
            source_ref=source_ref,
            observed_at=observed_at,
            actions=actions,
        )


class MemoryCuratorPlanNotFound(KeyError):
    """Raised when one observation has no curator recovery plan."""


class MemoryCuratorPlanCorruptError(ValueError):
    """Raised when a curator recovery plan cannot be trusted."""


class MemoryCuratorPlanLockContended(RuntimeError):
    """Raised when another process is mutating one observation's curator state."""


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

    def acquire(self) -> None:
        if self._handle is not None:
            return
        ensure_private_file(self.path)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            flock(handle.fileno(), LOCK_EX | LOCK_NB)
        except BlockingIOError:
            primary_error = MemoryCuratorPlanLockContended(
                "another process is mutating this observation's curator state"
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
    """Typed storage for recoverable observation decisions."""

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

    def get(self, observation_id: str) -> MemoryCuratorPlan | None:
        try:
            raw = self._collection.get(observation_id)
            if raw is None:
                return None
            return MemoryCuratorPlan.from_wire(
                {
                    key: value
                    for key, value in raw.items()
                    if key != "id"
                },
                expected_observation_id=observation_id,
                allowed_types=self._registry.names(),
            )
        except (
            TypeError,
            ValueError,
        ) as exc:
            self._raise_corrupt(observation_id, exc)

    def save(self, plan: MemoryCuratorPlan) -> MemoryCuratorPlan:
        self._collection.put(plan.observation_id, plan.to_wire())
        return plan

    def complete(self, observation_id: str) -> None:
        """Remove a completed plan while the caller holds its exclusive lock."""
        self._collection.delete(observation_id)

    def discard(self, observation_id: str) -> None:
        with self.exclusive(observation_id):
            with self._backend.transaction():
                if self._collection.get(observation_id) is None:
                    raise MemoryCuratorPlanNotFound(observation_id)
                self._collection.delete(observation_id)

    def exclusive(self, observation_id: str) -> MemoryCuratorPlanLock:
        """Return the authoritative mutation lock for one observation."""

        if not observation_id.startswith("obs_") or "/" in observation_id:
            raise ValueError(f"invalid observation id: {observation_id}")
        return MemoryCuratorPlanLock(
            self._paths.runtime_dir
            / "curator-locks"
            / f"{observation_id}.lock"
        )

    def _raise_corrupt(
        self,
        observation_id: str,
        exc: Exception,
    ) -> Never:
        report_corrupt_record(
            exc,
            component="memory",
            collection="memory_curator_plans",
            record_id=observation_id,
            project_root=self._paths.authority_root,
        )
        raise MemoryCuratorPlanCorruptError(
            f"invalid memory curator plan for observation {observation_id!r}; "
            "inspect with 'nuself memory plan show OBSERVATION' or explicitly "
            "discard with 'nuself memory plan discard OBSERVATION --force'"
        ) from exc
