"""Storage protocols, collection catalog, and opaque-key validation."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Protocol, runtime_checkable

from nuself.runtime.audit.types import LogComponent


# ── Protocols ─────────────────────────────────────────────────────────────


@runtime_checkable
class StorageCollection(Protocol):
    """One table-like collection within a storage backend."""

    def get(self, key: str) -> dict[str, object] | None: ...
    def put(self, key: str, value: dict[str, object]) -> None: ...
    def delete(self, key: str) -> None: ...
    def list(self) -> tuple[dict[str, object], ...]: ...
    def find(self, **filters: object) -> tuple[dict[str, object], ...]: ...


@runtime_checkable
class StorageBackend(Protocol):
    """Abstract storage backend."""
    def collection(self, name: str) -> StorageCollection: ...
    def transaction(self) -> AbstractContextManager[None]: ...


@runtime_checkable
class ClosableStorageBackend(StorageBackend, Protocol):
    """Storage backend whose lifetime is owned by a composition root."""

    def close(self) -> None: ...


# ── Known collection names ──────────────────────────────────────────────

COLLECTION_NAMES: tuple[str, ...] = (
    "memory_entries",
    "memory_candidates",
    "trace_nodes",
    "trace_edges",
    "reason_threads",
    "reason_steps",
    "persona_prompts",
    "profile_items",
    "source_documents",
    "source_chunks",
    "notification_outbox",
    "reflection_entries",
    "conversations",
    "memory_observations",
    "memory_curator_plans",
    "scheduler_state",
)

COLLECTION_LOG_COMPONENTS: dict[str, LogComponent] = {
    "memory_entries": "memory",
    "memory_candidates": "memory",
    "profile_items": "memory",
    "source_documents": "memory",
    "source_chunks": "memory",
    "persona_prompts": "persona",
    "reason_threads": "reasoning",
    "reason_steps": "reasoning",
    "trace_nodes": "reasoning",
    "trace_edges": "reasoning",
    "reflection_entries": "reflection",
    "notification_outbox": "outbox",
    "conversations": "chat",
    "memory_observations": "memory",
    "memory_curator_plans": "memory",
    "scheduler_state": "reflection",
}


def validate_storage_key(key: str) -> None:
    """Reject path syntax from one opaque collection record key."""

    if (
        key == ""
        or key in {".", ".."}
        or "\0" in key
        or "/" in key
        or "\\" in key
        or Path(key).is_absolute()
    ):
        raise ValueError("storage collection key is invalid")
