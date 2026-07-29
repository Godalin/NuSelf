"""Storage backend abstraction for durable NuSelf data.

Protocols + FileStorageBackend for v0.2.3.
SQLite backend added in v0.2.4.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from collections.abc import Generator
import os
from pathlib import Path
import threading
from typing import TYPE_CHECKING, Protocol, cast, runtime_checkable
from uuid import uuid4

from nuself.config import runtime_paths
from nuself.logs import LogComponent
from nuself.private_fs import (
    create_private_file,
    ensure_private_directory,
)
from nuself.runtime.observability import (
    report_corrupt_record,
)
from nuself.runtime import decode_json_value, encode_json_value
from nuself.storage_audit import report_backend_close_failure

if TYPE_CHECKING:
    from nuself.storage_sqlite import SqliteStorageBackend


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
}

# ── Collection → path mapping (v0.2.3 file layout) ──────────────────────

COLLECTION_DIR_MAP: dict[str, str] = {
    "memory_entries": "memory/entries",
    "memory_candidates": "memory/candidates",
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


class AtomicWriteCleanupError(RuntimeError):
    """An atomic write failed and its temporary artifact could not be removed."""

    def __init__(
        self,
        temporary_path: Path,
        *,
        primary_error: BaseException,
        cleanup_error: BaseException,
    ) -> None:
        super().__init__(
            "atomic write failed and temporary cleanup failed: "
            f"{temporary_path}"
        )
        self.temporary_path = temporary_path
        self.primary_error = primary_error
        self.cleanup_error = cleanup_error


class AtomicWriteDurabilityError(RuntimeError):
    """A replacement is visible but its directory entry may not be durable."""

    def __init__(
        self,
        destination_path: Path,
        *,
        sync_error: BaseException,
    ) -> None:
        super().__init__(
            "atomic destination replaced but directory synchronization failed: "
            f"{destination_path}"
        )
        self.destination_path = destination_path
        self.sync_error = sync_error


def _read_json_record(path: Path) -> dict[str, object]:
    raw = decode_json_value(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("stored record must be a JSON object")
    result: dict[str, object] = {}
    for key, value in cast("dict[str, object]", raw).items():
        result[key] = value
    return result


def _list_json_record(
    path: Path,
    *,
    collection: str,
    component: LogComponent,
    project_root: Path,
) -> dict[str, object] | None:
    try:
        return _read_json_record(path)
    except FileNotFoundError:
        return None
    except (ValueError, TypeError) as exc:
        report_corrupt_record(
            exc,
            component=component,
            collection=collection,
            record_id=path.stem or "<unknown>",
            project_root=project_root,
        )
        return None


def write_text_atomic(path: Path, text: str) -> None:
    """Privately replace UTF-8 text without exposing partial destination data."""

    ensure_private_directory(path.parent)
    tmp_path = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    temporary_created = False
    try:
        create_private_file(tmp_path)
        temporary_created = True
        tmp_path.write_text(text, encoding="utf-8")
        _sync_file(tmp_path)
        tmp_path.replace(path)
        temporary_created = False
        try:
            _sync_directory(path.parent)
        except BaseException as sync_error:
            raise AtomicWriteDurabilityError(
                path,
                sync_error=sync_error,
            ) from sync_error
    except BaseException as primary_error:
        if temporary_created:
            try:
                tmp_path.unlink()
            except FileNotFoundError:
                pass
            except BaseException as cleanup_error:
                raise AtomicWriteCleanupError(
                    tmp_path,
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
        raise


def _sync_file(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    encoded = encode_json_value(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=True,
    )
    write_text_atomic(
        path,
        encoded + "\n",
    )


class _FileCollection:
    """One collection backed by a directory of JSON files."""

    def __init__(
        self,
        directory: Path,
        *,
        name: str,
        component: LogComponent,
        project_root: Path,
    ) -> None:
        self._dir = directory
        self._name = name
        self._component: LogComponent = component
        self._project_root = project_root

    def get(self, key: str) -> dict[str, object] | None:
        path = self._dir / f"{key}.json"
        if not path.exists():
            return None
        return _read_json_record(path)

    def put(self, key: str, value: dict[str, object]) -> None:
        ensure_private_directory(self._dir)
        path = self._dir / f"{key}.json"
        write_json_atomic(path, value)

    def delete(self, key: str) -> None:
        path = self._dir / f"{key}.json"
        if path.exists():
            path.unlink()

    def list(self) -> tuple[dict[str, object], ...]:
        if not self._dir.exists():
            return ()
        items: list[dict[str, object]] = []
        for p in sorted(self._dir.rglob("*.json")):
            obj = _list_json_record(
                p,
                collection=self._name,
                component=self._component,
                project_root=self._project_root,
            )
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
        self,
        root: Path,
        collection_map: dict[str, str] | None = None,
        *,
        project_root: Path | None = None,
    ) -> None:
        self._root = root
        self._map = collection_map or COLLECTION_DIR_MAP
        self._project_root = (
            runtime_paths(project_root).project_root
            if project_root is not None
            else root.parent if root.name == "private" else root
        )
        self._transaction_lock = threading.RLock()

    def collection(self, name: str) -> _FileCollection:
        relative = self._map.get(name)
        if relative is None:
            raise ValueError(f"unknown collection: {name!r}")
        return _FileCollection(
            self._root / relative,
            name=name,
            component=COLLECTION_LOG_COMPONENTS[name],
            project_root=self._project_root,
        )

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Serialize a file-backed batch.

        Individual files remain atomic, but the filesystem backend cannot make
        a multi-file batch crash-atomic.
        """
        with self._transaction_lock:
            yield


# ── Factory helpers ──────────────────────────────────────────────────────


def create_file_backend(
    project_root: Path | None = None, *, root: Path | None = None
) -> FileStorageBackend:
    """Create a ``FileStorageBackend`` rooted at ``private/``."""
    base = root if root is not None else runtime_paths(project_root).private_root
    return FileStorageBackend(
        base,
        project_root=runtime_paths(project_root).project_root,
    )


def create_sqlite_backend(
    project_root: Path | None = None, *, db_path: Path | None = None
) -> SqliteStorageBackend:
    """Create a ``SqliteStorageBackend`` at ``private/nuself.sqlite`` (or *db_path*)."""
    from nuself.storage_sqlite import SqliteStorageBackend
    path = db_path if db_path is not None else runtime_paths(project_root).private_root / "nuself.sqlite"
    return SqliteStorageBackend(path, project_root=project_root)


def auto_backend(project_root: Path | None = None) -> StorageBackend:
    """Return ``SqliteStorageBackend`` if *nuself.sqlite* exists, else ``FileStorageBackend``."""
    paths = runtime_paths(project_root)
    db_path = paths.private_root / "nuself.sqlite"
    if db_path.exists():
        return create_sqlite_backend(project_root=project_root)
    return create_file_backend(project_root=project_root)


_default_backends: dict[Path, StorageBackend] = {}
_DEFAULT_BACKEND_LOCK = threading.Lock()


class DefaultBackendResetError(RuntimeError):
    """Raised after one or more owned default backends fail to close."""

    def __init__(self, failures: tuple[Exception, ...]) -> None:
        super().__init__(
            f"failed to close {len(failures)} default storage backend(s)"
        )
        self.failures = failures


def get_default_backend(project_root: Path | None = None) -> StorageBackend:
    """Return a lazily-created default backend scoped to one project root."""
    root = runtime_paths(project_root).project_root
    with _DEFAULT_BACKEND_LOCK:
        backend = _default_backends.get(root)
        if backend is None:
            backend = auto_backend(root)
            _default_backends[root] = backend
        return backend


def set_default_backend(
    backend: StorageBackend, project_root: Path | None = None
) -> None:
    """Override the process-global default backend (for tests or v0.2.4 migration)."""
    root = runtime_paths(project_root).project_root
    with _DEFAULT_BACKEND_LOCK:
        _default_backends[root] = backend


def reset_default_backend(project_root: Path | None = None) -> None:
    """Close and reset one default backend, or every backend when omitted."""
    with _DEFAULT_BACKEND_LOCK:
        if project_root is None:
            backends = tuple(_default_backends.items())
            _default_backends.clear()
        else:
            root = runtime_paths(project_root).project_root
            backend = _default_backends.pop(root, None)
            backends = ((root, backend),) if backend is not None else ()
    failures: list[Exception] = []
    for root, backend in backends:
        close = getattr(backend, "close", None)
        if callable(close):
            try:
                close()
            except Exception as exc:
                failures.append(exc)
                report_backend_close_failure(
                    exc,
                    project_root=root,
                    backend_type=type(backend).__name__,
                )
    if failures:
        raise DefaultBackendResetError(tuple(failures))


# ── Migration tools ──────────────────────────────────────────────────────


def migrate_collection(
    src: StorageBackend,
    dst: StorageBackend,
    name: str,
    *,
    clear_dst: bool = False,
) -> int:
    """Copy all items in *name* from *src* to *dst*. Returns item count."""
    src_col = src.collection(name)
    dst_col = dst.collection(name)

    if clear_dst:
        for item in dst_col.list():
            item_id = item.get("id")
            if isinstance(item_id, str):
                dst_col.delete(item_id)

    count = 0
    for item in src_col.list():
        item_id = item.get("id")
        if isinstance(item_id, str):
            dst_col.put(item_id, item)
            count += 1
    return count


def migrate_all(
    src: StorageBackend,
    dst: StorageBackend,
    *,
    collection_names: tuple[str, ...] | None = None,
    clear_dst: bool = False,
) -> dict[str, int]:
    """Migrate all known collections from *src* to *dst*.
    Returns ``{name: item_count}``.
    """
    names = collection_names or COLLECTION_NAMES
    result: dict[str, int] = {}
    for name in names:
        count = migrate_collection(src, dst, name, clear_dst=clear_dst)
        if count:
            result[name] = count
    return result
