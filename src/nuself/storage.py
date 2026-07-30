"""Storage backend abstraction for durable NuSelf data.

Protocols + FileStorageBackend for v0.2.3.
SQLite backend added in v0.2.4.
"""

from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from collections.abc import Callable, Generator
import fcntl
import os
from pathlib import Path
import threading
from typing import (
    TYPE_CHECKING,
    BinaryIO,
    Protocol,
    cast,
    runtime_checkable,
)
from uuid import uuid4

from nuself.config import runtime_paths
from nuself.logs import LogComponent
from nuself.private_fs import (
    create_private_file,
    ensure_private_directory,
    ensure_private_file,
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


class StorageMigrationValidationError(ValueError):
    """Authoritative file data cannot be migrated without loss."""


class FileStorageAuthorityError(RuntimeError):
    """File-backed storage authority is held by an incompatible operation."""


class SqliteStorageAuthorityError(FileStorageAuthorityError):
    """Canonical SQLite storage has already replaced file authority."""


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


class _FileCollection:
    """One collection backed by a directory of JSON files."""

    def __init__(
        self,
        directory: Path,
        *,
        name: str,
        component: LogComponent,
        project_root: Path,
        operation: Callable[[], AbstractContextManager[None]],
    ) -> None:
        self._dir = directory
        self._name = name
        self._component: LogComponent = component
        self._project_root = project_root
        self._operation = operation

    def get(self, key: str) -> dict[str, object] | None:
        with self._operation():
            path = self._record_path(key)
            if not path.exists():
                return None
            self._require_regular_record(path)
            return _read_json_record(path)

    def put(self, key: str, value: dict[str, object]) -> None:
        with self._operation():
            if "id" in value and value["id"] != key:
                raise ValueError(
                    "stored record id must equal its collection key"
                )
            self._ensure_collection_directory()
            path = self._record_path(key)
            if path.is_symlink():
                raise ValueError(
                    "file collection record must not be a symlink"
                )
            write_json_atomic(path, value)

    def delete(self, key: str) -> None:
        with self._operation():
            path = self._record_path(key)
            if path.exists():
                self._require_regular_record(path)
                delete_file_durable(path)
            elif path.is_symlink():
                raise ValueError(
                    "file collection record must not be a symlink"
                )

    def list(self) -> tuple[dict[str, object], ...]:
        with self._operation():
            if not self._dir.exists():
                return ()
            self._require_collection_directory()
            items: list[dict[str, object]] = []
            for p in sorted(self._dir.glob("*.json")):
                self._require_regular_record(p)
                obj = _list_json_record(
                    p,
                    collection=self._name,
                    component=self._component,
                    project_root=self._project_root,
                )
                if obj is not None:
                    items.append(obj)
            return tuple(items)

    def list_strict_for_migration(self) -> tuple[dict[str, object], ...]:
        """Read every authoritative record without corrupt-neighbor isolation."""
        with self._operation():
            if not self._dir.exists():
                return ()
            self._require_collection_directory()
            items: list[dict[str, object]] = []
            for path in sorted(self._dir.iterdir()):
                self._require_regular_record(path)
                if path.suffix != ".json":
                    raise StorageMigrationValidationError(
                        "file migration collection contains a non-JSON "
                        f"record: {path.name}"
                    )
                item = _read_json_record(path)
                item_id = item.get("id")
                if (
                    not isinstance(item_id, str)
                    or not item_id
                    or item_id != path.stem
                ):
                    raise StorageMigrationValidationError(
                        "file migration record id must be a non-empty string "
                        f"matching its filename: {path.name}"
                    )
                items.append(item)
            return tuple(items)

    def _record_path(self, key: str) -> Path:
        validate_storage_key(key)
        self._require_collection_directory_if_present()
        path = self._dir / f"{key}.json"
        if path.parent != self._dir:
            raise ValueError(
                "file collection record must be a direct child"
            )
        resolved_parent = path.parent.resolve(strict=False)
        collection = self._dir.resolve(strict=False)
        if resolved_parent != collection:
            raise ValueError(
                "file collection record escapes its collection"
            )
        return path

    def _ensure_collection_directory(self) -> None:
        self._require_collection_directory_if_present()
        ensure_private_directory(self._dir)
        self._require_collection_directory()

    def _require_collection_directory_if_present(self) -> None:
        if self._dir.is_symlink():
            raise ValueError(
                "file collection directory must not be a symlink"
            )
        if self._dir.exists() and not self._dir.is_dir():
            raise ValueError(
                "file collection path must be a directory"
            )

    def _require_collection_directory(self) -> None:
        self._require_collection_directory_if_present()
        if not self._dir.is_dir():
            raise ValueError("file collection directory is unavailable")

    @staticmethod
    def _require_regular_record(path: Path) -> None:
        if path.is_symlink():
            raise ValueError("file collection record must not be a symlink")
        if not path.is_file():
            raise ValueError(
                "file collection record must be a regular file"
            )

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
        _acquire_authority: bool = True,
    ) -> None:
        self._root = root
        self._map = collection_map or COLLECTION_DIR_MAP
        self._project_root = (
            runtime_paths(project_root).project_root
            if project_root is not None
            else root.parent if root.name == "private" else root
        )
        self._transaction_lock = threading.RLock()
        self._transaction_state = threading.local()
        self._transaction_lock_path = self._root / ".storage-transaction.lock"
        self._authority_handle: BinaryIO | None = None
        self._closed = False
        if _acquire_authority:
            self._authority_handle = _open_file_authority(
                self._root,
                exclusive=False,
            )

    def close(self) -> None:
        """Release this backend's shared file-authority lease."""
        with self._transaction_lock:
            if self._closed:
                return
            self._closed = True
            handle = self._authority_handle
            self._authority_handle = None
            if handle is None:
                return
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()

    def collection(self, name: str) -> _FileCollection:
        with self._operation():
            relative = self._map.get(name)
            if relative is None:
                raise ValueError(f"unknown collection: {name!r}")
            return _FileCollection(
                self._root / relative,
                name=name,
                component=COLLECTION_LOG_COMPONENTS[name],
                project_root=self._project_root,
                operation=self._operation,
            )

    @contextmanager
    def _operation(self) -> Generator[None, None, None]:
        with self._transaction_lock:
            self._require_open()
            yield

    def _require_open(self) -> None:
        if self._closed:
            raise RuntimeError("file storage backend is closed")

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Serialize a file-backed batch.

        Individual files remain atomic, but the filesystem backend cannot make
        a multi-file batch crash-atomic.
        """
        with self._transaction_lock:
            self._require_open()
            depth = getattr(self._transaction_state, "depth", 0)
            if depth > 0:
                self._transaction_state.depth = depth + 1
                try:
                    yield
                finally:
                    self._transaction_state.depth -= 1
                return

            ensure_private_file(self._transaction_lock_path)
            handle = self._transaction_lock_path.open("ab")
            locked = False
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                locked = True
                self._transaction_state.depth = 1
                yield
            finally:
                self._transaction_state.depth = 0
                if locked:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                handle.close()


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


def create_file_backend(
    project_root: Path | None = None,
    *,
    root: Path | None = None,
    _acquire_authority: bool = True,
) -> FileStorageBackend:
    """Create a ``FileStorageBackend`` rooted at ``private/``."""
    base = root if root is not None else runtime_paths(project_root).private_root
    return FileStorageBackend(
        base,
        project_root=runtime_paths(project_root).project_root,
        _acquire_authority=_acquire_authority,
    )


def open_sqlite_backend(
    project_root: Path | None = None, *, db_path: Path | None = None
) -> SqliteStorageBackend:
    """Open an existing SQLite backend without creating its database."""
    from nuself.storage_sqlite import SqliteStorageBackend
    paths = runtime_paths(project_root)
    canonical = paths.private_root / "nuself.sqlite"
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


def auto_backend(project_root: Path | None = None) -> StorageBackend:
    """Return ``SqliteStorageBackend`` if *nuself.sqlite* exists, else ``FileStorageBackend``."""
    paths = runtime_paths(project_root)
    db_path = paths.private_root / "nuself.sqlite"
    if db_path.exists() or db_path.is_symlink():
        return open_sqlite_backend(project_root=project_root)
    try:
        return create_file_backend(project_root=project_root)
    except SqliteStorageAuthorityError:
        return open_sqlite_backend(project_root=project_root)


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

    source_items = (
        src_col.list_strict_for_migration()
        if isinstance(src_col, _FileCollection)
        else src_col.list()
    )
    count = 0
    for item in source_items:
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise StorageMigrationValidationError(
                f"{name} record id must be a non-empty string"
            )
        upgraded = _upgrade_legacy_wire(name, item)
        dst_col.put(item_id, upgraded)
        if dst_col.get(item_id) != upgraded:
            raise StorageMigrationValidationError(
                f"{name} record failed post-write validation: {item_id}"
            )
        count += 1
    return count


_LEGACY_MEMORY_COLLECTIONS = frozenset(
    {"memory_entries", "memory_candidates", "profile_items"}
)


def _upgrade_legacy_wire(
    collection_name: str,
    item: dict[str, object],
) -> dict[str, object]:
    """Normalize persisted 0.2.x shapes at the explicit migration boundary."""
    if collection_name not in _LEGACY_MEMORY_COLLECTIONS:
        return item

    upgraded = dict(item)
    _upgrade_legacy_relations(upgraded)
    payload = upgraded.get("payload")
    if isinstance(payload, dict):
        payload_wire = cast(dict[str, object], payload)
        upgraded_payload: dict[str, object] = dict(payload_wire)
        _upgrade_legacy_relations(upgraded_payload)
        upgraded["payload"] = upgraded_payload
    return upgraded


def _upgrade_legacy_relations(data: dict[str, object]) -> None:
    relations = data.get("relations")
    if relations is not None and not isinstance(relations, dict):
        return
    upgraded_relations: dict[str, object]
    if isinstance(relations, dict):
        upgraded_relations = dict(cast(dict[str, object], relations))
    else:
        upgraded_relations = {}
    mappings = (
        ("supersedes", "supersedes"),
        ("related_memory_ids", "related_to"),
    )
    changed = False
    for legacy_name, relation_name in mappings:
        legacy_targets = data.get(legacy_name)
        if not isinstance(legacy_targets, list):
            continue
        data.pop(legacy_name)
        current_targets = upgraded_relations.get(relation_name)
        merged: list[object] = (
            list(cast(list[object], current_targets))
            if isinstance(current_targets, list)
            else []
        )
        for target in cast(list[object], legacy_targets):
            if target not in merged:
                merged.append(target)
        upgraded_relations[relation_name] = merged
        changed = True
    if changed:
        data["relations"] = upgraded_relations


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


def migrate_file_backend_atomically(
    project_root: Path | None = None,
) -> tuple[dict[str, int], Path]:
    """Migrate authoritative files and atomically publish one new SQLite DB."""
    paths = runtime_paths(project_root)
    destination_path = paths.private_root / "nuself.sqlite"
    with _exclusive_file_authority(paths.private_root):
        return _migrate_file_backend_with_authority(
            paths.project_root,
            destination_path=destination_path,
        )


def _migrate_file_backend_with_authority(
    project_root: Path,
    *,
    destination_path: Path,
) -> tuple[dict[str, int], Path]:
    conflicting_paths = (
        destination_path,
        *(
            destination_path.with_name(
                f"{destination_path.name}{suffix}"
            )
            for suffix in ("-wal", "-shm", "-journal")
        ),
    )
    if any(
        path.exists() or path.is_symlink()
        for path in conflicting_paths
    ):
        raise FileExistsError(
            "file migration destination or SQLite sidecar already exists; "
            f"move or remove it before migrating: {destination_path}"
        )
    ensure_private_directory(destination_path.parent)
    temporary = destination_path.with_name(
        f"{destination_path.name}.migrating-{uuid4().hex}"
    )
    source = create_file_backend(
        project_root,
        _acquire_authority=False,
    )
    destination: SqliteStorageBackend | None = None
    published = False
    try:
        destination = _create_sqlite_backend(
            project_root,
            db_path=temporary,
        )
        with source.transaction(), destination.transaction():
            result = migrate_all(source, destination)
        destination.close()
        destination = None
        _remove_sqlite_migration_sidecars(temporary)
        _sync_file(temporary)
        os.replace(temporary, destination_path)
        published = True
        try:
            _sync_directory(destination_path.parent)
        except BaseException as sync_error:
            raise AtomicWriteDurabilityError(
                destination_path,
                sync_error=sync_error,
            ) from sync_error
        return result, destination_path
    except BaseException as primary_error:
        if destination is not None:
            try:
                destination.close()
            except BaseException as close_error:
                raise AtomicWriteCleanupError(
                    temporary,
                    primary_error=primary_error,
                    cleanup_error=close_error,
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


@contextmanager
def _exclusive_file_authority(
    private_root: Path,
) -> Generator[None, None, None]:
    handle = _open_file_authority(private_root, exclusive=True)
    try:
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _open_file_authority(
    private_root: Path,
    *,
    exclusive: bool,
) -> BinaryIO:
    ensure_private_directory(private_root)
    lock_path = private_root / ".storage-authority.lock"
    ensure_private_file(lock_path)
    handle = lock_path.open("ab")
    operation = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    try:
        fcntl.flock(handle.fileno(), operation | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        role = "migration" if exclusive else "file-backed runtime"
        raise FileStorageAuthorityError(
            f"cannot start {role} while file storage authority is active"
        ) from exc
    if not exclusive:
        canonical_database = private_root / "nuself.sqlite"
        if canonical_database.exists() or canonical_database.is_symlink():
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
            raise SqliteStorageAuthorityError(
                "cannot start file storage after SQLite authority publication"
            )
    return handle


def _remove_sqlite_migration_sidecars(database: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        database.with_name(f"{database.name}{suffix}").unlink(
            missing_ok=True
        )


def _remove_sqlite_migration_artifacts(database: Path) -> None:
    database.unlink(missing_ok=True)
    _remove_sqlite_migration_sidecars(database)
