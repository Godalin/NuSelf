"""Live SQLite backend, transaction, schema, lease, and backup primitives."""

from __future__ import annotations

import fcntl
import os
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, cast

from nuself.runtime.audit.types import LogComponent
from nuself.storage.filesystem import (
    PRIVATE_FILE_MODE,
    ensure_private_directory,
    ensure_private_file,
    harden_private_file,
    require_private_file,
)
from nuself.runtime.messages import (
    decode_json_value,
    encode_json_value,
    freeze_json_value,
    thaw_json_value,
)
from nuself.runtime.diagnostics import (
    diagnostic_exception_message,
)
from nuself.runtime.observability import report_corrupt_record
from nuself.storage.contract import (
    COLLECTION_LOG_COMPONENTS,
    COLLECTION_NAMES,
)

_SQLITE_INITIALIZATION_LOCK = threading.Lock()
SQLITE_SCHEMA_VERSION = 7
_V2_COLLECTION_NAMES = (
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


def _json(v: object) -> str:
    return encode_json_value(
        v,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def _from_json(value: str) -> object:
    return decode_json_value(value)


def _collection_table(name: str) -> str:
    return f"col_{name}"

def _identifier(value: str) -> str:
    """Quote one SQLite identifier."""
    return '"' + value.replace('"', '""') + '"'


class _TransactionState:
    def __init__(self) -> None:
        self.local = threading.local()

    @property
    def depth(self) -> int:
        value = getattr(self.local, "depth", 0)
        return value if isinstance(value, int) else 0

    @depth.setter
    def depth(self, value: int) -> None:
        self.local.depth = value

    @property
    def rollback_only(self) -> bool:
        value = getattr(self.local, "rollback_only", False)
        return value if isinstance(value, bool) else False

    @rollback_only.setter
    def rollback_only(self, value: bool) -> None:
        self.local.rollback_only = value


class SqliteTransactionRollbackOnlyError(RuntimeError):
    """Raised when a caught inner failure prevents the outer commit."""


class SqliteTransactionCleanupError(RuntimeError):
    """Raised when rollback fails while preserving the primary cause."""

    def __init__(
        self,
        *,
        primary_error: BaseException,
        rollback_error: BaseException,
    ) -> None:
        super().__init__(
            "SQLite rollback failed after "
            f"{type(primary_error).__name__}: "
            f"{diagnostic_exception_message(rollback_error)}"
        )
        self.primary_error = primary_error
        self.rollback_error = rollback_error


class SqliteStorageLifecycleError(RuntimeError):
    """Base class for explicit SQLite backend lifecycle failures."""


class SqliteStorageCheckpointError(SqliteStorageLifecycleError):
    """Raised after close succeeds but the requested WAL checkpoint fails."""


class SqliteStorageCloseError(SqliteStorageLifecycleError):
    """Raised when the connection cannot be closed."""

    def __init__(
        self,
        message: str,
        *,
        checkpoint_error: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.checkpoint_error = checkpoint_error


class SqliteStorageInitializationCleanupError(
    SqliteStorageLifecycleError
):
    """Raised when a failed initialization also cannot release its connection."""

    def __init__(
        self,
        message: str,
        *,
        cleanup_error: Exception,
    ) -> None:
        super().__init__(message)
        self.cleanup_error = cleanup_error


class SqliteStorageBackupCleanupError(SqliteStorageLifecycleError):
    """Raised when a failed backup also cannot release its destination."""

    def __init__(
        self,
        *,
        backup_error: BaseException,
        cleanup_error: Exception,
    ) -> None:
        super().__init__(
            "SQLite backup failed and its destination connection "
            "could not be closed"
        )
        self.backup_error = backup_error
        self.cleanup_error = cleanup_error


class SqliteStorageUnsupportedVersionError(
    SqliteStorageLifecycleError
):
    """Raised when a database is newer than this runtime."""


class SqliteStorageIdentityError(SqliteStorageLifecycleError):
    """Raised when an existing database is not a NuSelf authority."""


class SqliteSchemaValidationError(ValueError):
    """A SQLite file does not contain a compatible NuSelf schema."""


class _SqliteWalCheckpointBusyError(RuntimeError):
    """Internal diagnostic for a checkpoint that returned SQLITE_BUSY."""


class _Lock(Protocol):
    def acquire(self) -> bool: ...
    def release(self) -> None: ...


class SqliteCollection:
    """One logical collection in the shared compact records table."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        lock: _Lock,
        transaction_state: _TransactionState,
        *,
        collection_name: str,
        component: LogComponent,
        project_root: Path,
    ) -> None:
        self._conn = conn
        self._lock = lock
        self._transaction_state = transaction_state
        self._collection_name = collection_name
        self._component: LogComponent = component
        self._project_root = project_root

    @staticmethod
    def _decode(record_id: object, payload_text: object) -> dict[str, object]:
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("stored SQLite row id is invalid")
        if not isinstance(payload_text, str):
            raise ValueError("stored SQLite payload is not JSON text")
        payload = _from_json(payload_text)
        if not isinstance(payload, dict) or "id" in payload:
            raise ValueError("stored SQLite payload is invalid")
        return {"id": record_id, **cast(dict[str, object], payload)}

    def _decode_rows(
        self, rows: list[tuple[object, ...]]
    ) -> tuple[dict[str, object], ...]:
        items: list[dict[str, object]] = []
        for row in rows:
            try:
                items.append(self._decode(row[0], row[1]))
            except (ValueError, TypeError) as exc:
                report_corrupt_record(
                    exc,
                    component=self._component,
                    collection=self._collection_name,
                    record_id=row[0] if row and isinstance(row[0], str) else "<unknown>",
                    project_root=self._project_root,
                )
        return tuple(items)

    def get(self, key: str) -> dict[str, object] | None:
        self._lock.acquire()
        try:
            row = self._conn.execute(
                "SELECT id, payload FROM records "
                "WHERE collection = ? AND id = ?",
                (self._collection_name, key),
            ).fetchone()
            return None if row is None else self._decode(row[0], row[1])
        finally:
            self._lock.release()

    def put(self, key: str, value: dict[str, object]) -> None:
        value_id = value.get("id")
        if value_id is not None and (
            not isinstance(value_id, str) or value_id != key
        ):
            raise ValueError("storage record id must be a string matching its key")
        validated = cast(
            dict[str, object], thaw_json_value(freeze_json_value(value))
        )
        payload = {
            field: field_value
            for field, field_value in validated.items()
            if field != "id"
        }
        self._lock.acquire()
        try:
            self._conn.execute(
                "INSERT INTO records(collection, id, payload) VALUES (?, ?, ?) "
                "ON CONFLICT(collection, id) DO UPDATE "
                "SET payload = excluded.payload",
                (self._collection_name, key, _json(payload)),
            )
            self._commit_if_standalone()
        finally:
            self._lock.release()

    def delete(self, key: str) -> None:
        self._lock.acquire()
        try:
            self._conn.execute(
                "DELETE FROM records WHERE collection = ? AND id = ?",
                (self._collection_name, key),
            )
            self._commit_if_standalone()
        finally:
            self._lock.release()

    def _commit_if_standalone(self) -> None:
        if self._transaction_state.depth == 0:
            self._conn.commit()

    def list(self) -> tuple[dict[str, object], ...]:
        self._lock.acquire()
        try:
            return self._list_locked()
        finally:
            self._lock.release()

    def _list_locked(self) -> tuple[dict[str, object], ...]:
        rows = self._conn.execute(
            "SELECT id, payload FROM records WHERE collection = ?",
            (self._collection_name,),
        ).fetchall()
        return self._decode_rows(rows)

    def find(self, **filters: object) -> tuple[dict[str, object], ...]:
        self._lock.acquire()
        try:
            return tuple(
                item
                for item in self._list_locked()
                if all(item.get(key) == expected for key, expected in filters.items())
            )
        finally:
            self._lock.release()


class SqliteStorageBackend:
    """Storage backend backed by a single SQLite database file."""

    def __init__(
        self,
        db_path: Path,
        *,
        project_root: Path | None = None,
        _initialize: bool = False,
        _managed: bool | None = None,
        _truncate_on_close: bool = False,
    ) -> None:
        self._db_path = db_path
        self._project_root = (
            project_root.absolute()
            if project_root is not None
            else db_path.parent.absolute()
        )
        canonical = self._project_root / "nuself.sqlite"
        self._managed = (
            db_path.absolute() == canonical.absolute()
            if _managed is None
            else _managed
        )
        if self._managed:
            ensure_private_directory(db_path.parent)
        require_private_file(db_path)
        if not _initialize:
            _validate_existing_nuself_database(db_path)
        if self._managed:
            harden_private_file(db_path)
        self._conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
        )
        self._lock = threading.RLock()
        self._transaction_state = _TransactionState()
        self._closed = False
        self._truncate_on_close = _truncate_on_close
        try:
            self._conn.execute("PRAGMA busy_timeout=5000")
            with _SQLITE_INITIALIZATION_LOCK:
                self._conn.execute("PRAGMA journal_mode=WAL")
                self._conn.execute("PRAGMA synchronous=NORMAL")
                self._init_schema(initialize=_initialize)
                if self._managed:
                    _harden_sqlite_sidecars(db_path)
        except BaseException as init_error:
            try:
                self._conn.close()
            except Exception as cleanup_error:
                raise SqliteStorageInitializationCleanupError(
                    "SQLite initialization failed and its connection "
                    "could not be closed",
                    cleanup_error=cleanup_error,
                ) from init_error
            self._closed = True
            raise

    @property
    def db_path(self) -> Path:
        return self._db_path

    def close(self) -> None:
        """Checkpoint and close the owned connection with truthful state."""
        with self._lock:
            if self._closed:
                return
            checkpoint_error: Exception | None = None
            try:
                checkpoint_mode = (
                    "TRUNCATE"
                    if self._truncate_on_close
                    else "PASSIVE"
                )
                checkpoint = self._conn.execute(
                    f"PRAGMA wal_checkpoint({checkpoint_mode})"
                ).fetchone()
                if (
                    checkpoint is None
                    or len(checkpoint) != 3
                    or any(type(value) is not int for value in checkpoint)
                ):
                    raise RuntimeError(
                        "SQLite WAL checkpoint returned an invalid status"
                    )
                busy, _, _ = checkpoint
                if busy and self._truncate_on_close:
                    raise _SqliteWalCheckpointBusyError(
                        "SQLite WAL checkpoint remained busy"
                    )
            except Exception as exc:
                checkpoint_error = exc
            try:
                self._conn.close()
            except sqlite3.Error as close_error:
                raise SqliteStorageCloseError(
                    "SQLite connection could not be closed",
                    checkpoint_error=checkpoint_error,
                ) from close_error
            self._closed = True
            if checkpoint_error is not None:
                raise SqliteStorageCheckpointError(
                    "SQLite connection closed after WAL checkpoint failed"
                ) from checkpoint_error

    def backup_to(
        self,
        destination: Path,
        *,
        managed: bool = False,
    ) -> None:
        """Write one consistent online backup and close its connection."""
        if destination.resolve() == self._db_path.resolve():
            raise ValueError("SQLite backup destination must differ from source")
        with self._lock:
            backup_connection_to_path(
                self._conn,
                destination,
                managed=managed,
            )

    def _init_schema(
        self,
        *,
        initialize: bool,
    ) -> None:
        if initialize:
            self._conn.execute(
                "CREATE TABLE _schema_version "
                "(version INTEGER NOT NULL)"
            )
        current_version = self._read_schema_version()
        self._require_supported_schema_version(current_version)
        if current_version < 1:
            if not initialize:
                raise SqliteStorageIdentityError(
                    "existing SQLite database has no applied schema"
                )
            self._apply_current_schema()
            self._conn.executemany(
                "INSERT INTO _schema_version (version) VALUES (?)",
                ((version,) for version in range(1, SQLITE_SCHEMA_VERSION + 1)),
            )
            self._conn.commit()
            current_version = SQLITE_SCHEMA_VERSION
        if current_version != SQLITE_SCHEMA_VERSION:
            raise SqliteStorageUnsupportedVersionError(
                "SQLite schema version "
                f"{current_version} requires explicit migration to version "
                f"{SQLITE_SCHEMA_VERSION}; run "
                "'uv run python -m scripts.migrate_database "
                f"{self._db_path} --to {SQLITE_SCHEMA_VERSION}'"
            )

    def _read_schema_version(self) -> int:
        row = self._conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM _schema_version"
        ).fetchone()
        current_version = (
            row[0] if row is not None and len(row) == 1 else None
        )
        if type(current_version) is not int or current_version < 0:
            raise SqliteStorageUnsupportedVersionError(
                "SQLite schema version is invalid"
            )
        return current_version

    @staticmethod
    def _require_supported_schema_version(
        current_version: int,
    ) -> None:
        if current_version > SQLITE_SCHEMA_VERSION:
            raise SqliteStorageUnsupportedVersionError(
                "SQLite schema version "
                f"{current_version} is newer than supported version "
                f"{SQLITE_SCHEMA_VERSION}"
            )

    def _apply_current_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE records (collection TEXT NOT NULL, id TEXT NOT NULL, "
            "payload TEXT NOT NULL CHECK(json_valid(payload) AND "
            "json_type(payload) = 'object'), "
            "PRIMARY KEY (collection, id)) WITHOUT ROWID"
        )
        self._conn.execute(
            "CREATE TABLE workspace_entries (namespace TEXT NOT NULL, "
            "key TEXT NOT NULL, value TEXT NOT NULL CHECK(json_valid(value) "
            "AND json_type(value) = 'object'), created_at TEXT NOT NULL, "
            "updated_at TEXT NOT NULL, PRIMARY KEY (namespace, key)) WITHOUT ROWID"
        )

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Run the outermost write batch as one SQLite transaction."""
        with self._lock:
            outermost = self._transaction_state.depth == 0
            if outermost:
                self._conn.execute("BEGIN IMMEDIATE")
                self._transaction_state.rollback_only = False
            self._transaction_state.depth += 1
            try:
                yield
            except BaseException as exc:
                self._transaction_state.depth -= 1
                self._transaction_state.rollback_only = True
                if outermost:
                    self._rollback_after_failure(exc)
                raise
            else:
                self._transaction_state.depth -= 1
                if not outermost:
                    return
                if self._transaction_state.rollback_only:
                    error = SqliteTransactionRollbackOnlyError(
                        "SQLite transaction cannot commit after a nested "
                        "transaction failure"
                    )
                    self._rollback_after_failure(error)
                    raise error
                try:
                    self._conn.commit()
                except BaseException as exc:
                    self._rollback_after_failure(exc)
                    raise
                self._reset_transaction_state()

    def _rollback_after_failure(
        self,
        primary_error: BaseException,
    ) -> None:
        try:
            self._conn.rollback()
        except BaseException as rollback_error:
            self._reset_transaction_state()
            raise SqliteTransactionCleanupError(
                primary_error=primary_error,
                rollback_error=rollback_error,
            ) from primary_error
        self._reset_transaction_state()

    def _reset_transaction_state(self) -> None:
        self._transaction_state.depth = 0
        self._transaction_state.rollback_only = False

    def collection(self, name: str) -> SqliteCollection:
        with self._lock:
            if name not in COLLECTION_NAMES:
                raise ValueError(f"unknown collection: {name!r}")
            return SqliteCollection(
                self._conn,
                self._lock,
                self._transaction_state,
                collection_name=name,
                component=COLLECTION_LOG_COMPONENTS[name],
                project_root=self._project_root,
            )

    def collection_names(self) -> tuple[str, ...]:
        return COLLECTION_NAMES

    def table_info(self, name: str) -> list[tuple[str, str, bool, str | None, bool]]:
        with self._lock:
            if name not in COLLECTION_NAMES:
                raise ValueError(f"unknown collection: {name!r}")
            table = "records"
            rows = self._conn.execute(
                f"PRAGMA table_info({_identifier(table)})"
            ).fetchall()
            return [
                (row[1], row[2], bool(row[3]), row[4], bool(row[5]))
                for row in rows
            ]


def backup_connection_to_path(
    source: sqlite3.Connection,
    destination: Path,
    *,
    managed: bool,
) -> None:
    _prepare_backup_destination(destination, managed=managed)
    backup = sqlite3.connect(str(destination))
    try:
        source.backup(backup)
    except BaseException as backup_error:
        try:
            backup.close()
        except Exception as cleanup_error:
            raise SqliteStorageBackupCleanupError(
                backup_error=backup_error,
                cleanup_error=cleanup_error,
            ) from backup_error
        raise
    backup.close()


def _prepare_backup_destination(
    destination: Path,
    *,
    managed: bool,
) -> None:
    if managed:
        ensure_private_file(destination)
        return
    if destination.exists() or destination.is_symlink():
        require_private_file(destination)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o666,
    )
    os.close(descriptor)


@contextmanager
def sqlite_schema_lease(
    database: Path,
    *,
    managed: bool,
) -> Generator[None, None, None]:
    """Serialize an existing database's schema upgrade across processes."""

    lock_path = database.with_name(f"{database.name}.schema.lock")
    descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
        PRIVATE_FILE_MODE if managed else 0o666,
    )
    try:
        if managed:
            os.fchmod(descriptor, PRIVATE_FILE_MODE)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)


def _harden_sqlite_sidecars(database: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        sidecar = database.with_name(f"{database.name}{suffix}")
        if sidecar.exists():
            ensure_private_file(sidecar)


def validate_nuself_schema(
    connection: sqlite3.Connection,
    *,
    authority: bool = False,
) -> int:
    """Validate NuSelf identity metadata without scanning stored content."""

    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
            if len(row) == 1 and isinstance(row[0], str)
        }
        if "_schema_version" not in tables:
            raise SqliteSchemaValidationError(
                "thought pack is missing NuSelf schema metadata"
            )
        version_info = connection.execute(
            "PRAGMA table_info(_schema_version)"
        ).fetchall()
        if tuple(
            (row[1], str(row[2]).upper(), row[3], row[5])
            for row in version_info
            if len(row) >= 6
        ) != (("version", "INTEGER", 1, 0),):
            raise SqliteSchemaValidationError(
                "thought pack has invalid NuSelf schema metadata"
            )
        version_rows = connection.execute(
            "SELECT version FROM _schema_version ORDER BY version"
        ).fetchall()
        versions = tuple(
            row[0]
            for row in version_rows
            if len(row) == 1 and type(row[0]) is int
        )
        if (
            len(versions) != len(version_rows)
            or not versions
            or versions != tuple(range(1, versions[-1] + 1))
        ):
            raise SqliteSchemaValidationError(
                "thought pack has an invalid schema version history"
            )
        version = versions[-1]
        if version > SQLITE_SCHEMA_VERSION:
            if authority:
                raise SqliteStorageUnsupportedVersionError(
                    "SQLite schema version "
                    f"{version} is newer than supported version "
                    f"{SQLITE_SCHEMA_VERSION}"
                )
            raise SqliteSchemaValidationError(
                f"thought pack schema version {version} is newer than "
                f"supported version {SQLITE_SCHEMA_VERSION}"
            )
        if version in (4, 5, 6, 7):
            expected_tables = {
                "_schema_version",
                "records",
                "workspace_entries",
            }
            if tables != expected_tables:
                raise SqliteSchemaValidationError(
                    "thought pack has invalid schema v4+ table set"
                )
            _validate_compact_table(
                connection,
                "records",
                secondary_index=(
                    ("idx_records_collection", "collection")
                    if version == 4
                    else None
                ),
            )
            _validate_compact_table(
                connection,
                "workspace_entries",
                secondary_index=(
                    ("idx_workspace_entries_ns", "namespace")
                    if version == 4
                    else None
                ),
            )
            if authority and version < SQLITE_SCHEMA_VERSION:
                raise SqliteStorageUnsupportedVersionError(
                    f"SQLite schema version {version} requires explicit migration"
                )
            return version
        required_collections = (
            COLLECTION_NAMES
            if version >= 3
            else _V2_COLLECTION_NAMES
        )
        for collection_name in required_collections:
            table = _collection_table(collection_name)
            if table not in tables:
                raise SqliteSchemaValidationError(
                    f"thought pack is missing collection table {table}"
                )
            table_info = connection.execute(
                f"PRAGMA table_info({_identifier(table)})"
            ).fetchall()
            if not any(
                len(column) >= 6
                and column[1] == "id"
                and column[5] == 1
                for column in table_info
            ):
                raise SqliteSchemaValidationError(
                    f"thought pack collection {table} has no id primary key"
                )
        if authority and version < SQLITE_SCHEMA_VERSION:
            raise SqliteStorageUnsupportedVersionError(
                "SQLite schema version "
                f"{version} requires explicit migration to supported version "
                f"{SQLITE_SCHEMA_VERSION}"
            )
        return version
    except SqliteSchemaValidationError:
        raise
    except sqlite3.DatabaseError as exc:
        raise SqliteSchemaValidationError(
            "thought pack is not a valid SQLite database"
        ) from exc


def _validate_compact_table(
    connection: sqlite3.Connection,
    table: str,
    *,
    secondary_index: tuple[str, str] | None,
) -> None:
    expected = {
        "records": (
            ("collection", "TEXT", 1, 1),
            ("id", "TEXT", 1, 2),
            ("payload", "TEXT", 1, 0),
        ),
        "workspace_entries": (
            ("namespace", "TEXT", 1, 1),
            ("key", "TEXT", 1, 2),
            ("value", "TEXT", 1, 0),
            ("created_at", "TEXT", 1, 0),
            ("updated_at", "TEXT", 1, 0),
        ),
    }[table]
    info = connection.execute(
        f"PRAGMA table_info({_identifier(table)})"
    ).fetchall()
    observed = tuple(
        (row[1], str(row[2]).upper(), row[3], row[5])
        for row in info
        if len(row) >= 6
    )
    json_column = "payload" if table == "records" else "value"
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    sql = row[0] if row is not None and len(row) == 1 else None
    normalized = " ".join(sql.upper().split()) if isinstance(sql, str) else ""
    if (
        observed != expected
        or "WITHOUT ROWID" not in normalized
        or f"JSON_VALID({json_column.upper()})" not in normalized
        or f"JSON_TYPE({json_column.upper()}) = 'OBJECT'" not in normalized
    ):
        raise SqliteSchemaValidationError(
            f"thought pack has invalid schema v4 table {table}"
        )
    indexes = connection.execute(
        f"PRAGMA index_list({_identifier(table)})"
    ).fetchall()
    secondary = tuple(
        (index[1], index[2], index[3], index[4])
        for index in indexes
        if len(index) >= 5 and index[3] != "pk"
    )
    expected_secondary = (
        ((secondary_index[0], 0, "c", 0),)
        if secondary_index is not None
        else ()
    )
    if secondary != expected_secondary:
        raise SqliteSchemaValidationError(
            f"thought pack has invalid schema v4+ indexes on {table}"
        )
    if secondary_index is not None:
        index_columns = connection.execute(
            f"PRAGMA index_info({_identifier(secondary_index[0])})"
        ).fetchall()
        if tuple(row[2] for row in index_columns) != (secondary_index[1],):
            raise SqliteSchemaValidationError(
                f"thought pack has invalid schema v4+ index on {table}"
            )


def _validate_existing_nuself_database(source: Path) -> int:
    """Validate live authority identity through a lock-aware connection."""

    try:
        with _readonly_authority_identity(source) as connection:
            return validate_nuself_schema(
                connection,
                authority=True,
            )
    except SqliteStorageUnsupportedVersionError:
        raise
    except SqliteSchemaValidationError as exc:
        raise SqliteStorageIdentityError(
            "existing SQLite database is not a valid NuSelf authority"
        ) from exc


@contextmanager
def _readonly_authority_identity(
    source: Path,
) -> Generator[sqlite3.Connection, None, None]:
    """Inspect live authority metadata with normal locking and WAL handling."""

    source_uri = f"{source.resolve().as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(source_uri, uri=True)
    except sqlite3.DatabaseError as exc:
        raise SqliteSchemaValidationError(
            "SQLite authority is not a readable database"
        ) from exc
    try:
        yield connection
    finally:
        connection.close()
