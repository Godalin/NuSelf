"""Storage backend abstraction for durable NuSelf data.

Protocols + FileStorageBackend for v0.2.3.
SQLite backend added in v0.2.4.
"""

from __future__ import annotations

import json
from pathlib import Path
import threading
from typing import Protocol, cast, runtime_checkable
from uuid import uuid4

from nuself.config import runtime_paths


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


# ── Collection → path mapping (v0.2.3 file layout) ──────────────────────

COLLECTION_DIR_MAP: dict[str, str] = {
    "memory_entries": "memory/entries",
    "memory_candidates": "memory/candidates",
    "memory_relations": "memory/relations",
    "trace_nodes": "traces/traces",
    "trace_edges": "traces/links",
    "reason_threads": "reasoning/threads",
    "reason_steps": "reasoning/steps",
    "persona_prompts": "persona_prompts",
    "profile_items": "profile/items",
    "source_documents": "sources/documents",
    "source_chunks": "sources/chunks",
    "notification_outbox": "notifications/outbox",
    "reflection_entries": "reflections",
}


# ── File implementation ──────────────────────────────────────────────────


def _safe_read_json(path: Path) -> dict[str, object] | None:
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            result: dict[str, object] = {}
            for k, v in cast("dict[str, object]", raw).items():
                result[k] = v
            return result
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    try:
        tmp_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(path)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


class _FileCollection:
    """One collection backed by a directory of JSON files."""

    def __init__(self, directory: Path) -> None:
        self._dir = directory

    def get(self, key: str) -> dict[str, object] | None:
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        return _safe_read_json(path)

    def put(self, key: str, value: dict[str, object]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"{key}.json"
        _write_json_atomic(path, value)

    def delete(self, key: str) -> None:
        path = self._dir / f"{key}.json"
        if path.exists():
            path.unlink()

    def list(self) -> tuple[dict[str, object], ...]:
        if not self._dir.exists():
            return ()
        items: list[dict[str, object]] = []
        for p in sorted(self._dir.iterdir()):
            if p.suffix == ".json":
                obj = _safe_read_json(p)
                if obj is not None:
                    items.append(obj)
        return tuple(items)

    def find(self, **filters: object) -> tuple[dict[str, object], ...]:
        items = self.list()
        if not filters:
            return items
        result: list[dict[str, object]] = []
        for item in items:
            for key, expected in filters.items():
                if item.get(key) != expected:
                    break
            else:
                result.append(item)
        return tuple(result)


class FileStorageBackend:
    """Storage backend that maps collections to directories of JSON files."""

    def __init__(
        self, root: Path, collection_map: dict[str, str] | None = None
    ) -> None:
        self._root = root
        self._map = collection_map or COLLECTION_DIR_MAP

    def collection(self, name: str) -> _FileCollection:
        relative = self._map.get(name)
        if relative is None:
            raise ValueError(f"unknown collection: {name!r}")
        return _FileCollection(self._root / relative)


# ── Factory helpers ──────────────────────────────────────────────────────


def create_file_backend(
    project_root: Path | None = None, *, root: Path | None = None
) -> FileStorageBackend:
    """Create a ``FileStorageBackend`` rooted at ``private/``."""
    base = root if root is not None else runtime_paths(project_root).private_root
    return FileStorageBackend(base)


_default_backend: StorageBackend | None = None
_DEFAULT_BACKEND_LOCK = threading.Lock()


def get_default_backend() -> StorageBackend:
    """Return the process-global default storage backend (lazily created)."""
    global _default_backend
    if _default_backend is None:
        with _DEFAULT_BACKEND_LOCK:
            if _default_backend is None:
                _default_backend = create_file_backend()
    return _default_backend


def set_default_backend(backend: StorageBackend) -> None:
    """Override the process-global default backend (for tests or v0.2.4 migration)."""
    global _default_backend
    _default_backend = backend


def reset_default_backend() -> None:
    """Reset the default backend so it is re-created on next access."""
    global _default_backend
    _default_backend = None
