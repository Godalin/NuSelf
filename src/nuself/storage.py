"""Storage abstractions and durable file helpers for NuSelf data."""

from __future__ import annotations

from contextlib import AbstractContextManager
import os
from pathlib import Path
import threading
from typing import (
    TYPE_CHECKING,
    Protocol,
    runtime_checkable,
)
from uuid import uuid4

from nuself.config import runtime_paths
from nuself.logs import LogComponent
from nuself.private_fs import (
    create_private_file,
    ensure_private_directory,
)
from nuself.runtime import encode_json_value
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
    "memory_curator_cursors",
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
    "memory_curator_cursors": "memory",
    "memory_curator_plans": "memory",
    "scheduler_state": "reflection",
}

# ── Durable filesystem helpers ───────────────────────────────────────────


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


class AtomicDeleteDurabilityError(RuntimeError):
    """An unlink is visible but its directory entry may not be durable."""

    def __init__(
        self,
        deleted_path: Path,
        *,
        sync_error: BaseException,
    ) -> None:
        super().__init__(
            "atomic destination deleted but directory synchronization failed: "
            f"{deleted_path}"
        )
        self.deleted_path = deleted_path
        self.sync_error = sync_error


class SqliteStorageAuthorityError(RuntimeError):
    """The selected SQLite authority could not be opened or initialized."""


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


def delete_file_durable(path: Path) -> bool:
    """Unlink one file and durably synchronize its parent directory."""

    try:
        path.unlink()
    except FileNotFoundError:
        return False
    try:
        _sync_directory(path.parent)
    except BaseException as sync_error:
        raise AtomicDeleteDurabilityError(
            path,
            sync_error=sync_error,
        ) from sync_error
    return True


def validate_storage_key(key: str) -> None:
    """Reject path syntax from one opaque file-collection record key."""

    if (
        key == ""
        or key in {".", ".."}
        or "\0" in key
        or "/" in key
        or "\\" in key
        or Path(key).is_absolute()
    ):
        raise ValueError("storage collection key is invalid")


# ── Factory helpers ──────────────────────────────────────────────────────


def open_sqlite_backend(
    project_root: Path | None = None, *, db_path: Path | None = None
) -> SqliteStorageBackend:
    """Open an existing SQLite backend without creating its database."""
    from nuself.storage_sqlite import SqliteStorageBackend
    paths = runtime_paths(project_root)
    canonical = paths.authority_root / "nuself.sqlite"
    path = db_path if db_path is not None else canonical
    managed = path.absolute() == canonical.absolute()
    return SqliteStorageBackend(
        path,
        project_root=paths.project_root,
        _managed=managed,
    )


def _create_sqlite_backend(
    project_root: Path | None = None,
    *,
    db_path: Path,
) -> SqliteStorageBackend:
    """Create one unpublished SQLite database for atomic migration."""
    create_private_file(db_path)
    from nuself.storage_sqlite import SqliteStorageBackend

    return SqliteStorageBackend(
        db_path,
        project_root=project_root,
        _initialize=True,
        _managed=True,
        _truncate_on_close=True,
    )


def auto_backend(project_root: Path | None = None) -> ClosableStorageBackend:
    """Open or atomically initialize the selected SQLite authority."""
    paths = runtime_paths(project_root)
    db_path = paths.authority_root / "nuself.sqlite"
    if db_path.exists() or db_path.is_symlink():
        return open_sqlite_backend(project_root=project_root)
    ensure_private_directory(db_path.parent)
    from nuself.storage_sqlite import sqlite_schema_lease

    with sqlite_schema_lease(db_path, managed=True):
        if not (db_path.exists() or db_path.is_symlink()):
            _initialize_sqlite_authority(paths.project_root)
    if db_path.exists() or db_path.is_symlink():
        return open_sqlite_backend(project_root=project_root)
    raise SqliteStorageAuthorityError(
        "SQLite authority initialization did not publish a database"
    )


def _initialize_sqlite_authority(project_root: Path) -> Path:
    paths = runtime_paths(project_root)
    destination = paths.database_file
    ensure_private_directory(destination.parent)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    temporary = destination.with_name(
        f"{destination.name}.initializing-{uuid4().hex}"
    )
    backend: SqliteStorageBackend | None = None
    published = False
    try:
        backend = _create_sqlite_backend(
            paths.project_root,
            db_path=temporary,
        )
        backend.close()
        backend = None
        _remove_sqlite_migration_sidecars(temporary)
        _sync_file(temporary)
        os.replace(temporary, destination)
        published = True
        _sync_directory(destination.parent)
        return destination
    except BaseException as primary_error:
        if backend is not None:
            try:
                backend.close()
            except BaseException as cleanup_error:
                raise AtomicWriteCleanupError(
                    temporary,
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
        if not published:
            try:
                _remove_sqlite_migration_artifacts(temporary)
            except BaseException as cleanup_error:
                raise AtomicWriteCleanupError(
                    temporary,
                    primary_error=primary_error,
                    cleanup_error=cleanup_error,
                ) from primary_error
        raise


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


def _remove_sqlite_migration_sidecars(database: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        database.with_name(f"{database.name}{suffix}").unlink(
            missing_ok=True
        )
    database.with_name(f"{database.name}.schema.lock").unlink(
        missing_ok=True
    )


def _remove_sqlite_migration_artifacts(database: Path) -> None:
    database.unlink(missing_ok=True)
    _remove_sqlite_migration_sidecars(database)
