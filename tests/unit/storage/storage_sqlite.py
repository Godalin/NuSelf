"""Tests for SqliteStorageBackend and SqliteCollection."""

from __future__ import annotations

from notification_fixtures import notification_outbox

# pyright: reportUnusedImport=false

from memory_fixtures import (
    memory_candidate_repository,
    memory_entry_repository,
    source_repository,
)

# pyright: reportPrivateUsage=false

import json
from concurrent.futures import ThreadPoolExecutor
import multiprocessing
from multiprocessing.context import SpawnContext
from multiprocessing.synchronize import Event
import os
from pathlib import Path
import sqlite3
import stat
import subprocess
import sys
import threading
import time
from typing import Callable, cast

import pytest

import nuself.storage_sqlite as sqlite_storage
from nuself.logs import read_log_events
from nuself.notification import NotificationOutbox
from nuself.memory.repository import (
    MemoryCandidateRepository,
    MemoryEntryRepository,
)
from nuself.memory.source_repository import SourceRepository
from nuself.application import compose_trace_services
from nuself.config import runtime_paths
from nuself.profile.repository import ProfileItemRepository
from nuself.reason.repository import ReasonRepository
from nuself.reflection.repository import ReflectionRepository
from nuself.storage import (
    _create_sqlite_backend as create_sqlite_backend,
    DefaultBackendResetError,
    auto_backend,
    StorageBackend,
    get_default_backend,
    open_sqlite_backend,
    reset_default_backend,
    set_default_backend,
)
from nuself.storage_sqlite import (
    COLLECTION_NAMES,
    SqliteStorageBackend,
    SqliteStorageBackupCleanupError,
    SqliteStorageCheckpointError,
    SqliteStorageCloseError,
    SqliteStorageInitializationCleanupError,
    SqliteStorageIdentityError,
    SqliteStorageUnsupportedVersionError,
    SqliteTransactionCleanupError,
    SqliteTransactionRollbackOnlyError,
    inspect_sqlite_thought_pack,
)


def _sqlite_table_names(database: Path) -> tuple[str, ...]:
    connection = sqlite3.connect(
        f"{database.resolve().as_uri()}?mode=ro",
        uri=True,
    )
    try:
        return tuple(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' ORDER BY name"
            ).fetchall()
            if len(row) == 1 and isinstance(row[0], str)
        )
    finally:
        connection.close()


def _open_automatically(project: Path, database: Path) -> object:
    del database
    return auto_backend(project)


def _open_explicitly(project: Path, database: Path) -> object:
    return open_sqlite_backend(project, db_path=database)


def _open_directly(project: Path, database: Path) -> object:
    return SqliteStorageBackend(database, project_root=project)


def _spawn_context() -> SpawnContext:
    return multiprocessing.get_context("spawn")


def _initialize_authority_and_write(
    project_root: str,
    start: Event,
    index: int,
) -> None:
    if not start.wait(timeout=30):
        raise RuntimeError("parent did not start authority initialization")
    backend = auto_backend(Path(project_root))
    try:
        backend.collection("memory_entries").put(
            f"initializer-{index}",
            {"id": f"initializer-{index}", "sequence": index},
        )
    finally:
        assert isinstance(backend, SqliteStorageBackend)
        backend.close()


def _write_and_checkpoint_live_authority(
    project_root: str,
    ready: Event,
    start: Event,
) -> None:
    backend = auto_backend(Path(project_root))
    assert isinstance(backend, SqliteStorageBackend)
    ready.set()
    if not start.wait(timeout=30):
        raise RuntimeError("parent did not start SQLite stress run")
    try:
        collection = backend.collection("memory_entries")
        for index in range(200):
            collection.put(
                f"writer-{index}",
                {"id": f"writer-{index}", "sequence": index},
            )
            if index % 5 == 0:
                backend._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
            time.sleep(0.001)
    finally:
        backend.close()


def _commit_live_authority_then_crash(
    project_root: str,
    committed: Event,
) -> None:
    backend = auto_backend(Path(project_root))
    assert isinstance(backend, SqliteStorageBackend)
    backend._conn.execute("PRAGMA wal_autocheckpoint=0")
    backend.collection("memory_entries").put(
        "crash-wal",
        {"id": "crash-wal", "state": "committed"},
    )
    assert backend.db_path.with_name(
        f"{backend.db_path.name}-wal"
    ).exists()
    committed.set()
    os._exit(0)


def test_sqlite_backend_hardens_database_directory_and_sidecars(
    tmp_path: Path,
) -> None:
    private = tmp_path
    private.chmod(0o755)
    database = private / "nuself.sqlite"
    create_sqlite_backend(
        tmp_path,
        db_path=database,
    ).close()
    private.chmod(0o755)
    database.chmod(0o644)

    backend = SqliteStorageBackend(
        database,
        project_root=tmp_path,
    )
    try:
        backend.collection("memory_entries").put(
            "private",
            {"id": "private", "title": "Private"},
        )
        assert stat.S_IMODE(private.stat().st_mode) == 0o700
        assert stat.S_IMODE(database.stat().st_mode) == 0o600
        sidecars = list(private.glob("nuself.sqlite-*"))
        assert sidecars
        assert all(
            stat.S_IMODE(sidecar.stat().st_mode) == 0o600
            for sidecar in sidecars
        )
    finally:
        backend.close()


class TransactionConnectionProxy:
    def __init__(
        self,
        delegate: sqlite3.Connection,
        *,
        fail_commit: bool = False,
        fail_rollback: bool = False,
    ) -> None:
        self._delegate = delegate
        self._fail_commit = fail_commit
        self._fail_rollback = fail_rollback
        self.rollback_calls = 0

    def execute(self, sql: str) -> sqlite3.Cursor:
        return self._delegate.execute(sql)

    def commit(self) -> None:
        if self._fail_commit:
            raise sqlite3.OperationalError("commit unavailable")
        self._delegate.commit()

    def rollback(self) -> None:
        self.rollback_calls += 1
        if self._fail_rollback:
            raise sqlite3.OperationalError("rollback unavailable")
        self._delegate.rollback()


class LifecycleConnectionProxy:
    def __init__(
        self,
        delegate: sqlite3.Connection,
        *,
        fail_checkpoint: bool = False,
        fail_close: bool = False,
        fail_schema_init: bool = False,
        checkpoint_result: tuple[int, int, int] | None = None,
    ) -> None:
        self._delegate = delegate
        self.fail_checkpoint = fail_checkpoint
        self.fail_close = fail_close
        self.fail_schema_init = fail_schema_init
        self.checkpoint_result = checkpoint_result
        self.checkpoint_calls = 0
        self.close_calls = 0

    def execute(self, sql: str) -> sqlite3.Cursor:
        if sql.startswith("PRAGMA wal_checkpoint"):
            self.checkpoint_calls += 1
            if self.fail_checkpoint:
                raise sqlite3.OperationalError("checkpoint unavailable")
            if self.checkpoint_result is not None:
                return cast(
                    sqlite3.Cursor,
                    CheckpointCursor(self.checkpoint_result),
                )
        if self.fail_schema_init and sql.startswith("CREATE TABLE"):
            raise sqlite3.OperationalError("schema init unavailable")
        return self._delegate.execute(sql)

    def close(self) -> None:
        self.close_calls += 1
        if self.fail_close:
            raise sqlite3.OperationalError("close unavailable")
        self._delegate.close()


class CheckpointCursor:
    def __init__(self, result: tuple[int, int, int]) -> None:
        self._result = result

    def fetchone(self) -> tuple[int, int, int]:
        return self._result


class TrackingConnection(sqlite3.Connection):
    close_calls: int

    def close(self) -> None:
        self.close_calls += 1
        super().close()


class BackupFailingConnectionProxy:
    def __init__(self, error: BaseException) -> None:
        self.error = error

    def backup(self, target: sqlite3.Connection) -> None:
        del target
        raise self.error


class CloseBackend:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.close_calls = 0

    def collection(self, name: str) -> object:
        raise AssertionError(f"unexpected collection access: {name}")

    def transaction(self) -> object:
        raise AssertionError("unexpected transaction access")

    def close(self) -> None:
        self.close_calls += 1
        if self.error is not None:
            raise self.error


def _set_raw_sqlite_column(
    db_path: Path,
    *,
    table: str,
    record_id: str,
    column: str,
    value: object,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        if table.startswith("col_"):
            conn.execute("PRAGMA ignore_check_constraints=ON")
            conn.execute(
                "UPDATE records SET payload = ? "
                "WHERE collection = ? AND id = ?",
                (value, table.removeprefix("col_"), record_id),
            )
            conn.commit()
            return
        conn.execute(
            f'UPDATE "{table}" SET "{column}" = ? WHERE id = ?',
            (value, record_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_internal_sqlite_backend_creator_creates_db(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    assert isinstance(backend, SqliteStorageBackend)
    assert db_path.exists()


def test_open_sqlite_backend_requires_existing_database(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir(mode=0o755)
    external.chmod(0o755)
    db_path = external / "missing.sqlite"

    with pytest.raises(FileNotFoundError):
        open_sqlite_backend(db_path=db_path)

    assert not db_path.exists()
    assert stat.S_IMODE(external.stat().st_mode) == 0o755


def test_direct_sqlite_backend_requires_existing_database(
    tmp_path: Path,
) -> None:
    external = tmp_path / "external"
    external.mkdir(mode=0o755)
    external.chmod(0o755)
    db_path = external / "missing.sqlite"

    with pytest.raises(FileNotFoundError):
        SqliteStorageBackend(db_path)

    assert not db_path.exists()
    assert stat.S_IMODE(external.stat().st_mode) == 0o755


@pytest.mark.parametrize(
    "opener",
    [
        pytest.param(_open_automatically, id="auto-backend"),
        pytest.param(_open_explicitly, id="explicit-open"),
        pytest.param(_open_directly, id="direct-constructor"),
    ],
)
def test_sqlite_open_rejects_redirected_private_before_side_effects(
    tmp_path: Path,
    opener: Callable[[Path, Path], object],
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external"
    external.mkdir(mode=0o755)
    database = external / "nuself.sqlite"
    create_sqlite_backend(db_path=database).close()
    external.chmod(0o755)
    database.chmod(0o644)
    before_bytes = database.read_bytes()
    before_tables = _sqlite_table_names(database)
    before_entries = tuple(
        sorted(path.name for path in external.iterdir())
    )
    authority = project / ".nuself"
    authority.symlink_to(
        external,
        target_is_directory=True,
    )

    with pytest.raises(OSError, match="actual directory"):
        opener(authority, authority / "nuself.sqlite")

    assert database.read_bytes() == before_bytes
    assert stat.S_IMODE(database.stat().st_mode) == 0o644
    assert stat.S_IMODE(external.stat().st_mode) == 0o755
    assert _sqlite_table_names(database) == before_tables
    assert tuple(
        sorted(path.name for path in external.iterdir())
    ) == before_entries


@pytest.mark.parametrize(
    "kind",
    ["empty", "ordinary-sqlite", "incomplete-nuself"],
)
@pytest.mark.parametrize(
    "opener",
    [
        pytest.param(_open_automatically, id="auto-backend"),
        pytest.param(_open_explicitly, id="explicit-open"),
        pytest.param(_open_directly, id="direct-constructor"),
    ],
)
def test_open_rejects_unrecognized_database_without_mutation(
    tmp_path: Path,
    kind: str,
    opener: Callable[[Path, Path], object],
) -> None:
    private = tmp_path
    database = private / "nuself.sqlite"
    if kind == "empty":
        database.touch()
    else:
        connection = sqlite3.connect(database)
        try:
            if kind == "ordinary-sqlite":
                connection.execute("CREATE TABLE unrelated (value TEXT)")
            else:
                connection.execute(
                    "CREATE TABLE _schema_version "
                    "(version INTEGER NOT NULL)"
                )
                connection.execute(
                    "INSERT INTO _schema_version VALUES (2)"
                )
            connection.commit()
        finally:
            connection.close()
    database.chmod(0o644)
    before_bytes = database.read_bytes()
    before_tables = _sqlite_table_names(database)

    with pytest.raises(
        SqliteStorageIdentityError,
        match="not a valid NuSelf authority",
    ):
        opener(tmp_path, database)

    assert database.read_bytes() == before_bytes
    assert stat.S_IMODE(database.stat().st_mode) == 0o644
    assert _sqlite_table_names(database) == before_tables
    assert not database.with_name(f"{database.name}-wal").exists()
    assert not database.with_name(f"{database.name}-shm").exists()
    assert not database.with_name(f"{database.name}-journal").exists()


def test_shared_connection_read_waits_for_transaction_commit(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "shared.sqlite")
    collection = backend.collection("memory_entries")
    write_visible_to_owner = threading.Event()
    release_transaction = threading.Event()
    read_finished = threading.Event()
    observed: list[dict[str, object] | None] = []

    def write() -> None:
        with backend.transaction():
            collection.put("pending", {"id": "pending", "value": 1})
            write_visible_to_owner.set()
            assert release_transaction.wait(timeout=5)

    def read() -> None:
        assert write_visible_to_owner.wait(timeout=5)
        observed.append(collection.get("pending"))
        read_finished.set()

    writer = threading.Thread(target=write)
    reader = threading.Thread(target=read)
    writer.start()
    reader.start()
    assert write_visible_to_owner.wait(timeout=5)
    assert not read_finished.wait(timeout=0.1)
    release_transaction.set()
    writer.join(timeout=5)
    reader.join(timeout=5)

    assert not writer.is_alive()
    assert not reader.is_alive()
    assert observed == [{"id": "pending", "value": 1}]
    backend.close()


def test_shared_connection_read_never_observes_rolled_back_write(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "rollback.sqlite")
    collection = backend.collection("memory_entries")
    write_visible_to_owner = threading.Event()
    release_transaction = threading.Event()
    read_finished = threading.Event()
    observed: list[dict[str, object] | None] = []

    def write() -> None:
        with pytest.raises(RuntimeError, match="rollback"):
            with backend.transaction():
                collection.put(
                    "rolled-back",
                    {"id": "rolled-back", "value": 1},
                )
                write_visible_to_owner.set()
                assert release_transaction.wait(timeout=5)
                raise RuntimeError("rollback")

    def read() -> None:
        assert write_visible_to_owner.wait(timeout=5)
        observed.append(collection.get("rolled-back"))
        read_finished.set()

    writer = threading.Thread(target=write)
    reader = threading.Thread(target=read)
    writer.start()
    reader.start()
    assert write_visible_to_owner.wait(timeout=5)
    assert not read_finished.wait(timeout=0.1)
    release_transaction.set()
    writer.join(timeout=5)
    reader.join(timeout=5)

    assert not writer.is_alive()
    assert not reader.is_alive()
    assert observed == [None]
    backend.close()


def test_running_backend_reads_columns_added_by_another_backend(
    tmp_path: Path,
) -> None:
    database = tmp_path / "shared-schema.sqlite"
    first = create_sqlite_backend(db_path=database)
    second = open_sqlite_backend(db_path=database)
    first_collection = first.collection("notification_outbox")
    second_collection = second.collection("notification_outbox")
    try:
        first_collection.put("entry", {"id": "entry", "title": "before"})
        assert first_collection.get("entry") == {
            "id": "entry",
            "title": "before",
        }

        second_collection.put(
            "entry",
            {
                "id": "entry",
                "title": "after",
                "required_adapters": ["email"],
            },
        )

        assert first_collection.get("entry") == {
            "id": "entry",
            "title": "after",
            "required_adapters": ["email"],
        }
        assert first_collection.list() == (
            {
                "id": "entry",
                "title": "after",
                "required_adapters": ["email"],
            },
        )
    finally:
        second.close()
        first.close()


def test_sqlite_put_rejects_record_id_mismatch(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "identity.sqlite")
    collection = backend.collection("memory_entries")
    try:
        with pytest.raises(
            ValueError,
            match="string matching its key",
        ):
            collection.put("expected", {"id": "different"})

        assert collection.get("expected") is None
    finally:
        backend.close()


def test_default_backend_is_scoped_by_project_root(tmp_path: Path) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    try:
        first = get_default_backend(first_root)
        second = get_default_backend(second_root)
        assert first is get_default_backend(first_root)
        assert second is get_default_backend(second_root)
        assert first is not second

        first.collection("memory_entries").put(
            "only-first", {"id": "only-first"}
        )
        assert (
            second.collection("memory_entries").get("only-first") is None
        )
    finally:
        reset_default_backend()


def test_notification_outbox_uses_explicit_authority_backend(
    tmp_path: Path,
) -> None:
    backend = auto_backend(tmp_path)
    outbox = NotificationOutbox(runtime_paths(tmp_path), backend)

    assert outbox._backend is backend


def test_reset_closes_backend_used_by_default_repository(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(
        tmp_path,
        db_path=tmp_path / "nuself.sqlite",
    )
    set_default_backend(backend, tmp_path)
    repository = memory_entry_repository(tmp_path)
    backend.collection("memory_entries").put(
        "lifecycle-probe",
        {"id": "lifecycle-probe", "title": "probe"},
    )

    reset_default_backend(tmp_path)

    assert getattr(backend, "_closed") is True
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        repository.list()


def test_candidate_repository_uses_explicit_backend(
    tmp_path: Path,
) -> None:
    repository = memory_candidate_repository(
        tmp_path,
        backend=auto_backend(tmp_path / "isolated"),
    )

    assert repository.list() == []


def test_reset_default_backend_attempts_every_owned_close(
    tmp_path: Path,
) -> None:
    failed = CloseBackend(error=RuntimeError("first close failed"))
    healthy = CloseBackend()
    set_default_backend(cast(StorageBackend, failed), tmp_path / "first")
    set_default_backend(cast(StorageBackend, healthy), tmp_path / "second")

    with pytest.raises(
        DefaultBackendResetError,
        match="failed to close 1 default storage backend",
    ) as captured:
        reset_default_backend()

    assert failed.close_calls == 1
    assert healthy.close_calls == 1
    assert captured.value.failures == (failed.error,)
    [event] = read_log_events(
        project_root=tmp_path / "first",
        component="storage",
    )
    assert event.event == "backend_close_failed"
    assert event.status == "degraded"
    assert event.error == "first close failed"
    assert event.metadata == {"backend_type": "CloseBackend"}


def test_close_is_idempotent_after_connection_closes(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    original = cast(sqlite3.Connection, getattr(backend, "_conn"))
    proxy = LifecycleConnectionProxy(original)
    setattr(backend, "_conn", cast(sqlite3.Connection, proxy))

    backend.close()
    backend.close()

    assert proxy.checkpoint_calls == 1
    assert proxy.close_calls == 1


def test_online_backup_includes_wal_data_and_closes_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = create_sqlite_backend(db_path=tmp_path / "source.sqlite")
    source_connection = cast(
        sqlite3.Connection,
        getattr(source, "_conn"),
    )
    source_connection.execute("PRAGMA wal_autocheckpoint=0")
    source.collection("memory_entries").put(
        "wal-entry",
        {"id": "wal-entry", "title": "Committed in WAL"},
    )
    original_connect = sqlite3.connect
    destinations: list[TrackingConnection] = []

    def tracking_connect(
        database: str,
    ) -> sqlite3.Connection:
        connection = original_connect(
            database,
            factory=TrackingConnection,
        )
        tracked = connection
        tracked.close_calls = 0
        destinations.append(tracked)
        return tracked

    monkeypatch.setattr(
        "nuself.storage_sqlite.sqlite3.connect",
        tracking_connect,
    )
    destination = tmp_path / "exports" / "snapshot.sqlite"

    try:
        source.backup_to(destination)
        source.collection("memory_entries").put(
            "wal-entry",
            {"id": "wal-entry", "title": "Updated WAL data"},
        )
        source.backup_to(destination)
    finally:
        source.close()

    assert len(destinations) == 2
    assert all(
        connection.close_calls == 1
        for connection in destinations
    )
    monkeypatch.undo()
    snapshot = SqliteStorageBackend(destination)
    try:
        assert snapshot.collection("memory_entries").get(
            "wal-entry"
        ) == {
            "id": "wal-entry",
            "title": "Updated WAL data",
        }
    finally:
        snapshot.close()


def test_backup_to_external_preserves_parent_and_file_modes(
    tmp_path: Path,
) -> None:
    source = create_sqlite_backend(
        db_path=tmp_path / "source.sqlite",
    )
    source.collection("memory_entries").put(
        "entry",
        {"id": "entry", "title": "Backup"},
    )
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)
    destination = shared / "snapshot.sqlite"
    destination.touch(mode=0o644)
    destination.chmod(0o644)

    try:
        source.backup_to(destination)
    finally:
        source.close()

    assert stat.S_IMODE(shared.stat().st_mode) == 0o755
    assert stat.S_IMODE(destination.stat().st_mode) == 0o644
    snapshot = SqliteStorageBackend(destination)
    try:
        assert snapshot.collection("memory_entries").get(
            "entry"
        ) == {
            "id": "entry",
            "title": "Backup",
        }
    finally:
        snapshot.close()


def test_backup_and_destination_close_failure_retain_both_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "source.sqlite")
    original_source = cast(
        sqlite3.Connection,
        getattr(backend, "_conn"),
    )
    backup_error = RuntimeError("backup failed")
    source = BackupFailingConnectionProxy(backup_error)
    raw_destination = sqlite3.connect(
        tmp_path / "destination.sqlite"
    )
    destination = LifecycleConnectionProxy(
        raw_destination,
        fail_close=True,
    )

    def connect_destination(database: str) -> sqlite3.Connection:
        del database
        return cast(sqlite3.Connection, destination)

    monkeypatch.setattr(
        "nuself.storage_sqlite.sqlite3.connect",
        connect_destination,
    )
    setattr(backend, "_conn", cast(sqlite3.Connection, source))

    try:
        with pytest.raises(
            SqliteStorageBackupCleanupError
        ) as captured:
            backend.backup_to(tmp_path / "backup.sqlite")
    finally:
        setattr(backend, "_conn", original_source)
        raw_destination.close()
        backend.close()

    assert captured.value.backup_error is backup_error
    assert captured.value.cleanup_error is not None
    assert captured.value.__cause__ is backup_error
    assert destination.close_calls == 1


def test_backend_rejects_future_schema_version(
    tmp_path: Path,
) -> None:
    database = tmp_path / "future.sqlite"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "CREATE TABLE _schema_version (version INTEGER NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO _schema_version VALUES (?)",
            ((version,) for version in range(1, 100)),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        SqliteStorageUnsupportedVersionError,
        match="newer than supported version",
    ):
        SqliteStorageBackend(database)


def test_readonly_inspection_closes_source_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "inspect.sqlite"
    create_sqlite_backend(db_path=database).close()
    original_connect = sqlite3.connect
    connections: list[TrackingConnection] = []

    def tracking_connect(
        path: str,
        *,
        uri: bool = False,
    ) -> sqlite3.Connection:
        connection = original_connect(
            path,
            uri=uri,
            factory=TrackingConnection,
        )
        connection.close_calls = 0
        connections.append(connection)
        return connection

    monkeypatch.setattr(
        "nuself.storage_sqlite.sqlite3.connect",
        tracking_connect,
    )

    inspection = inspect_sqlite_thought_pack(database)

    assert inspection.schema_version == 5
    assert inspection.total_items == 0
    assert len(connections) == 1
    assert connections[0].close_calls == 1


def test_checkpoint_failure_is_raised_after_connection_closes(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    original = cast(sqlite3.Connection, getattr(backend, "_conn"))
    proxy = LifecycleConnectionProxy(original, fail_checkpoint=True)
    setattr(backend, "_conn", cast(sqlite3.Connection, proxy))

    with pytest.raises(
        SqliteStorageCheckpointError,
        match="closed after WAL checkpoint failed",
    ) as captured:
        backend.close()

    assert isinstance(captured.value.__cause__, sqlite3.OperationalError)
    assert str(captured.value.__cause__) == "checkpoint unavailable"
    assert proxy.close_calls == 1
    backend.close()
    assert proxy.close_calls == 1


def test_busy_checkpoint_status_is_raised_after_connection_closes(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    original = cast(sqlite3.Connection, getattr(backend, "_conn"))
    proxy = LifecycleConnectionProxy(
        original,
        checkpoint_result=(1, 4, 2),
    )
    setattr(backend, "_conn", cast(sqlite3.Connection, proxy))

    with pytest.raises(SqliteStorageCheckpointError) as captured:
        backend.close()

    assert isinstance(captured.value.__cause__, RuntimeError)
    assert str(captured.value.__cause__) == (
        "SQLite WAL checkpoint remained busy"
    )
    assert proxy.close_calls == 1


def test_close_failure_is_visible_and_retryable(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    original = cast(sqlite3.Connection, getattr(backend, "_conn"))
    proxy = LifecycleConnectionProxy(original, fail_close=True)
    setattr(backend, "_conn", cast(sqlite3.Connection, proxy))

    with pytest.raises(
        SqliteStorageCloseError,
        match="connection could not be closed",
    ) as captured:
        backend.close()

    assert isinstance(captured.value.__cause__, sqlite3.OperationalError)
    assert str(captured.value.__cause__) == "close unavailable"
    proxy.fail_close = False
    backend.close()
    assert proxy.close_calls == 2


def test_close_failure_retains_checkpoint_diagnostic(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    original = cast(sqlite3.Connection, getattr(backend, "_conn"))
    proxy = LifecycleConnectionProxy(
        original,
        fail_checkpoint=True,
        fail_close=True,
    )
    setattr(backend, "_conn", cast(sqlite3.Connection, proxy))

    with pytest.raises(SqliteStorageCloseError) as captured:
        backend.close()

    checkpoint_error = captured.value.checkpoint_error
    assert isinstance(checkpoint_error, sqlite3.OperationalError)
    assert str(checkpoint_error) == "checkpoint unavailable"
    proxy.fail_checkpoint = False
    proxy.fail_close = False
    backend.close()


def test_initialization_cleanup_preserves_both_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = sqlite3.connect(tmp_path / "delegate.sqlite")
    proxy = LifecycleConnectionProxy(
        connection,
        fail_close=True,
        fail_schema_init=True,
    )

    def connect_proxy(
        *args: object,
        **kwargs: object,
    ) -> sqlite3.Connection:
        return cast(sqlite3.Connection, proxy)

    monkeypatch.setattr(sqlite3, "connect", connect_proxy)

    with pytest.raises(
        SqliteStorageInitializationCleanupError,
        match="initialization failed",
    ) as captured:
        create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")

    assert isinstance(captured.value.__cause__, sqlite3.OperationalError)
    assert str(captured.value.__cause__) == "schema init unavailable"
    assert isinstance(
        captured.value.cleanup_error,
        sqlite3.OperationalError,
    )
    assert str(captured.value.cleanup_error) == "close unavailable"
    proxy.fail_close = False
    proxy.close()


def test_concurrent_backend_initialization_waits_for_wal_setup(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    create_sqlite_backend(db_path=db_path).close()

    def open_backend(_: int) -> SqliteStorageBackend:
        return SqliteStorageBackend(db_path)

    with ThreadPoolExecutor(max_workers=8) as executor:
        backends = tuple(
            executor.map(open_backend, range(16))
        )

    assert all(backend.collection("memory_entries").list() == () for backend in backends)
    for backend in backends:
        backend.close()


def test_cross_process_missing_authority_initializes_once_without_lost_writes(
    tmp_path: Path,
) -> None:
    context = _spawn_context()
    start = context.Event()
    processes = tuple(
        context.Process(
            target=_initialize_authority_and_write,
            args=(str(tmp_path), start, index),
        )
        for index in range(8)
    )
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=30)
        assert process.exitcode == 0

    backend = auto_backend(tmp_path)
    try:
        records = backend.collection("memory_entries").list()
        assert {record["id"] for record in records} == {
            f"initializer-{index}" for index in range(8)
        }
    finally:
        assert isinstance(backend, SqliteStorageBackend)
        backend.close()
    assert not tuple(tmp_path.glob("nuself.sqlite.initializing-*"))


def test_authority_open_does_not_run_thought_pack_integrity_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = tmp_path / "nuself.sqlite"
    create_sqlite_backend(tmp_path, db_path=database).close()

    def unexpected_integrity_scan(
        connection: sqlite3.Connection,
    ) -> int:
        del connection
        raise AssertionError("ordinary authority open ran quick_check")

    monkeypatch.setattr(
        sqlite_storage,
        "_validate_thought_pack_connection",
        unexpected_integrity_scan,
    )

    open_sqlite_backend(tmp_path).close()


def test_external_sqlite_open_preserves_parent_and_file_modes(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    database = shared / "pack.sqlite"
    create_sqlite_backend(db_path=database).close()
    shared.chmod(0o755)
    database.chmod(0o644)

    backend = open_sqlite_backend(db_path=database)
    try:
        assert stat.S_IMODE(shared.stat().st_mode) == 0o755
        assert stat.S_IMODE(database.stat().st_mode) == 0o644
    finally:
        backend.close()

    assert stat.S_IMODE(shared.stat().st_mode) == 0o755
    assert stat.S_IMODE(database.stat().st_mode) == 0o644


def test_cross_process_live_writer_checkpoint_and_repeated_open(
    tmp_path: Path,
) -> None:
    database = tmp_path / "nuself.sqlite"
    create_sqlite_backend(tmp_path, db_path=database).close()
    context = _spawn_context()
    ready = context.Event()
    start = context.Event()
    writer = context.Process(
        target=_write_and_checkpoint_live_authority,
        args=(str(tmp_path), ready, start),
    )
    writer.start()
    assert ready.wait(timeout=30)
    start.set()

    open_count = 0
    deadline = time.monotonic() + 20
    while (
        writer.is_alive() or open_count < 20
    ) and time.monotonic() < deadline:
        backend = cast(
            SqliteStorageBackend,
            auto_backend(tmp_path),
        )
        try:
            assert isinstance(backend, SqliteStorageBackend)
            backend.collection("memory_entries").list()
        finally:
            backend.close()
        open_count += 1

    writer.join(timeout=30)
    assert writer.exitcode == 0
    assert open_count >= 20

    final = cast(
        SqliteStorageBackend,
        auto_backend(tmp_path),
    )
    try:
        assert len(final.collection("memory_entries").list()) == 200
    finally:
        final.close()


def test_open_recovers_committed_uncheckpointed_wal_after_crash(
    tmp_path: Path,
) -> None:
    database = tmp_path / "nuself.sqlite"
    create_sqlite_backend(tmp_path, db_path=database).close()
    context = _spawn_context()
    committed = context.Event()
    writer = context.Process(
        target=_commit_live_authority_then_crash,
        args=(str(tmp_path), committed),
    )
    writer.start()
    assert committed.wait(timeout=30)
    writer.join(timeout=30)
    assert writer.exitcode == 0
    assert database.with_name(f"{database.name}-wal").exists()

    backend = cast(
        SqliteStorageBackend,
        auto_backend(tmp_path),
    )
    try:
        assert backend.collection("memory_entries").get(
            "crash-wal"
        ) == {
            "id": "crash-wal",
            "state": "committed",
        }
    finally:
        backend.close()


@pytest.mark.parametrize("name", COLLECTION_NAMES)
def test_all_known_collections_available(tmp_path: Path, name: str) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection(name)
    assert col.list() == ()


def test_unknown_collection_raises(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    with pytest.raises(ValueError, match="unknown collection"):
        backend.collection("nonexistent")


def test_put_and_get(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("mem_001", {"id": "mem_001", "title": "Test", "value": 42})
    result = col.get("mem_001")
    assert result is not None
    assert result["id"] == "mem_001"
    assert result["title"] == "Test"
    assert result["value"] == 42


def test_json_null_round_trips_as_present_none(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put(
        "mem_null",
        {"id": "mem_null", "nullable": None},
    )

    assert col.get("mem_null") == {
        "id": "mem_null",
        "nullable": None,
    }
    assert col.list() == (
        {"id": "mem_null", "nullable": None},
    )


def test_list_isolates_corrupt_sqlite_json_row(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    col = backend.collection("memory_entries")
    healthy: dict[str, object] = {
        "id": "healthy",
        "title": "Readable",
        "type": "belief",
    }
    col.put("healthy", healthy)
    col.put(
        "corrupt",
        {"id": "corrupt", "title": "Before", "type": "belief"},
    )
    _set_raw_sqlite_column(
        db_path,
        table="col_memory_entries",
        record_id="corrupt",
        column="title",
        value="private corrupt text",
    )

    assert col.list() == (healthy,)

    event = read_log_events(
        project_root=tmp_path,
        component="memory",
    )[-1]
    assert event.event == "record_decode_failed"
    assert event.metadata == {
        "collection": "memory_entries",
        "record_id": "corrupt",
    }
    assert "private corrupt text" not in str(event.to_record())
    with pytest.raises(
        ValueError,
        match="Expecting value",
    ):
        col.get("corrupt")


def test_find_isolates_matching_corrupt_sqlite_row(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    col = backend.collection("memory_entries")
    healthy: dict[str, object] = {
        "id": "healthy",
        "title": "Readable",
        "type": "belief",
    }
    col.put("healthy", healthy)
    col.put(
        "corrupt",
        {"id": "corrupt", "title": "Before", "type": "belief"},
    )
    _set_raw_sqlite_column(
        db_path,
        table="col_memory_entries",
        record_id="corrupt",
        column="title",
        value="not-json",
    )

    assert col.find(type="belief") == (healthy,)
    event = read_log_events(
        project_root=tmp_path,
        component="memory",
    )[-1]
    assert event.metadata == {
        "collection": "memory_entries",
        "record_id": "corrupt",
    }


def test_direct_get_rejects_non_text_dynamic_column(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    col = backend.collection("memory_entries")
    col.put("corrupt", {"id": "corrupt", "title": "Before"})
    _set_raw_sqlite_column(
        db_path,
        table="col_memory_entries",
        record_id="corrupt",
        column="title",
        value=sqlite3.Binary(b"private bytes"),
    )

    with pytest.raises(
        ValueError,
        match="payload is not JSON text",
    ):
        col.get("corrupt")


def test_get_missing_returns_none(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    assert col.get("nonexistent") is None


def test_put_overwrites(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("mem_001", {"id": "mem_001", "value": 1})
    col.put("mem_001", {"id": "mem_001", "value": 2})
    result = col.get("mem_001")
    assert result is not None
    assert result["value"] == 2


def test_invalid_put_preserves_row_and_does_not_add_columns(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("mem_001", {"id": "mem_001", "value": "old"})

    with pytest.raises(TypeError, match="floats must be finite"):
        col.put(
            "mem_001",
            {
                "id": "mem_001",
                "new_field": float("inf"),
            },
        )

    assert col.get("mem_001") == {"id": "mem_001", "value": "old"}
    assert "new_field" not in {
        column[0] for column in backend.table_info("memory_entries")
    }


def test_get_rejects_non_standard_numeric_constants(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    col = backend.collection("memory_entries")
    col.put("mem_001", {"id": "mem_001", "value": "old"})
    _set_raw_sqlite_column(
        db_path,
        table="col_memory_entries",
        record_id="mem_001",
        column="value",
        value="NaN",
    )

    with pytest.raises(ValueError, match="invalid"):
        col.get("mem_001")


def test_put_replaces_and_removes_omitted_fields(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("mem_001", {"id": "mem_001", "value": 1, "obsolete": True})
    col.put("mem_001", {"id": "mem_001", "value": 2})
    assert col.get("mem_001") == {"id": "mem_001", "value": 2}


def test_delete(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("mem_001", {"id": "mem_001"})
    col.delete("mem_001")
    assert col.get("mem_001") is None


def test_delete_missing_does_not_raise(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.delete("nonexistent")  # should not raise


def test_list_empty(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    assert col.list() == ()


def test_list_multiple(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("a", {"id": "a", "order": 1})
    col.put("b", {"id": "b", "order": 2})
    items = col.list()
    assert len(items) == 2
    ids = {item["id"] for item in items}
    assert ids == {"a", "b"}


def test_find_no_filters_returns_all(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("a", {"id": "a", "type": "x"})
    col.put("b", {"id": "b", "type": "y"})
    assert len(col.find()) == 2


def test_find_with_filters(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    col.put("a", {"id": "a", "type": "belief", "status": "active"})
    col.put("b", {"id": "b", "type": "concept", "status": "active"})
    col.put("c", {"id": "c", "type": "belief", "status": "archived"})

    beliefs = col.find(type="belief")
    assert len(beliefs) == 2

    active_beliefs = col.find(type="belief", status="active")
    assert len(active_beliefs) == 1
    assert active_beliefs[0]["id"] == "a"


def test_collections_are_independent(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    entries = backend.collection("memory_entries")
    candidates = backend.collection("memory_candidates")
    entries.put("mem_001", {"id": "mem_001"})
    assert candidates.get("mem_001") is None
    assert entries.get("mem_001") is not None


def test_reuses_same_db(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend1 = create_sqlite_backend(db_path=db_path)
    backend1.collection("memory_entries").put("mem_001", {"id": "mem_001", "data": "hello"})

    backend2 = open_sqlite_backend(db_path=db_path)
    result = backend2.collection("memory_entries").get("mem_001")
    assert result is not None
    assert result["data"] == "hello"


def test_thread_safe_put(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")

    def put_item(i: int) -> None:
        col.put(f"key_{i}", {"id": f"key_{i}", "value": i})

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(put_item, range(32)))

    items = col.list()
    assert len(items) == 32


def test_concurrent_backends_expand_same_dynamic_schema_once(
    tmp_path: Path,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    db_path = tmp_path / "nuself.sqlite"
    create_sqlite_backend(db_path=db_path).close()
    backends = tuple(SqliteStorageBackend(db_path) for _ in range(8))
    barrier = Barrier(len(backends))

    def put_item(index: int) -> None:
        collection = backends[index].collection("persona_prompts")
        barrier.wait()
        collection.put(
            f"persona-{index}",
            {
                "id": f"persona-{index}",
                "name": f"Persona {index}",
                "prompt": f"Prompt {index}",
            },
        )

    with ThreadPoolExecutor(max_workers=len(backends)) as pool:
        list(pool.map(put_item, range(len(backends))))

    records = backends[0].collection("persona_prompts").list()
    assert {record["id"] for record in records} == {
        f"persona-{index}" for index in range(len(backends))
    }


def test_transaction_rolls_back_all_collection_writes(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    entries = backend.collection("memory_entries")
    candidates = backend.collection("memory_candidates")

    with pytest.raises(RuntimeError, match="stop"):
        with backend.transaction():
            entries.put("mem_001", {"id": "mem_001", "title": "rolled back"})
            candidates.put("mc_001", {"id": "mc_001", "title": "rolled back"})
            raise RuntimeError("stop")

    assert entries.get("mem_001") is None
    assert candidates.get("mc_001") is None


def test_nested_transaction_commits_once(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    with backend.transaction():
        col.put("a", {"id": "a", "value": 1})
        with backend.transaction():
            col.put("b", {"id": "b", "value": 2})
    assert {item["id"] for item in col.list()} == {"a", "b"}


def test_caught_nested_failure_makes_outer_transaction_rollback_only(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")

    with pytest.raises(
        SqliteTransactionRollbackOnlyError,
        match="cannot commit after a nested transaction failure",
    ):
        with backend.transaction():
            try:
                with backend.transaction():
                    col.put("inner", {"id": "inner", "value": 1})
                    raise RuntimeError("inner failed")
            except RuntimeError:
                pass
            col.put("outer", {"id": "outer", "value": 2})

    assert col.get("inner") is None
    assert col.get("outer") is None

    with backend.transaction():
        col.put("recovered", {"id": "recovered", "value": 3})
    assert col.get("recovered") is not None


def test_keyboard_interrupt_rolls_back_and_restores_transaction_state(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")

    with pytest.raises(KeyboardInterrupt):
        with backend.transaction():
            col.put("interrupted", {"id": "interrupted", "value": 1})
            raise KeyboardInterrupt

    assert col.get("interrupted") is None
    with backend.transaction():
        col.put("after", {"id": "after", "value": 2})
    assert col.get("after") is not None


def test_commit_failure_rolls_back_and_preserves_primary_error(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    original = cast(
        sqlite3.Connection,
        getattr(backend, "_conn"),
    )
    proxy = TransactionConnectionProxy(original, fail_commit=True)
    setattr(backend, "_conn", cast(sqlite3.Connection, proxy))

    with pytest.raises(
        sqlite3.OperationalError,
        match="commit unavailable",
    ):
        with backend.transaction():
            col.put("not-committed", {"id": "not-committed"})

    assert proxy.rollback_calls == 1
    assert col.get("not-committed") is None

    setattr(backend, "_conn", original)
    with backend.transaction():
        col.put("recovered", {"id": "recovered"})
    assert col.get("recovered") is not None


def test_rollback_failure_retains_primary_commit_cause(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    original = cast(
        sqlite3.Connection,
        getattr(backend, "_conn"),
    )
    proxy = TransactionConnectionProxy(
        original,
        fail_commit=True,
        fail_rollback=True,
    )
    setattr(backend, "_conn", cast(sqlite3.Connection, proxy))

    with pytest.raises(
        SqliteTransactionCleanupError,
        match="rollback unavailable",
    ) as captured:
        with backend.transaction():
            col.put("not-committed", {"id": "not-committed"})

    assert isinstance(captured.value.__cause__, sqlite3.OperationalError)
    assert str(captured.value.__cause__) == "commit unavailable"
    assert captured.value.primary_error is captured.value.__cause__
    assert isinstance(
        captured.value.rollback_error,
        sqlite3.OperationalError,
    )
    assert str(captured.value.rollback_error) == "rollback unavailable"
    assert proxy.rollback_calls == 1

    setattr(backend, "_conn", original)
    original.rollback()


def test_transaction_cleanup_error_redacts_rollback_diagnostic() -> None:
    secret = "sk-rollback-secret-value"
    primary_error = RuntimeError("transaction failed")
    rollback_error = OSError(f"rollback rejected api_key={secret}")

    error = SqliteTransactionCleanupError(
        primary_error=primary_error,
        rollback_error=rollback_error,
    )

    assert error.primary_error is primary_error
    assert error.rollback_error is rollback_error
    assert secret not in str(error)
    assert "api_key=***" in str(error)


@pytest.mark.parametrize(
    "primary_error",
    [
        RuntimeError("body failed"),
        KeyboardInterrupt(),
    ],
)
def test_rollback_failure_retains_transaction_body_base_exception(
    tmp_path: Path,
    primary_error: BaseException,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    original = cast(
        sqlite3.Connection,
        getattr(backend, "_conn"),
    )
    proxy = TransactionConnectionProxy(
        original,
        fail_rollback=True,
    )
    setattr(backend, "_conn", cast(sqlite3.Connection, proxy))

    with pytest.raises(SqliteTransactionCleanupError) as captured:
        with backend.transaction():
            col.put("not-committed", {"id": "not-committed"})
            raise primary_error

    error = captured.value
    assert error.primary_error is primary_error
    assert error.__cause__ is primary_error
    assert isinstance(error.rollback_error, sqlite3.OperationalError)
    assert str(error.rollback_error) == "rollback unavailable"
    assert proxy.rollback_calls == 1

    setattr(backend, "_conn", original)
    original.rollback()
    with backend.transaction():
        col.put("recovered", {"id": "recovered"})
    assert col.get("recovered") is not None


def test_rollback_failure_retains_rollback_only_error_and_resets_state(
    tmp_path: Path,
) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    original = cast(
        sqlite3.Connection,
        getattr(backend, "_conn"),
    )
    proxy = TransactionConnectionProxy(
        original,
        fail_rollback=True,
    )
    setattr(backend, "_conn", cast(sqlite3.Connection, proxy))

    with pytest.raises(SqliteTransactionCleanupError) as captured:
        with backend.transaction():
            try:
                with backend.transaction():
                    col.put("inner", {"id": "inner"})
                    raise RuntimeError("inner failed")
            except RuntimeError:
                pass

    error = captured.value
    assert isinstance(
        error.primary_error,
        SqliteTransactionRollbackOnlyError,
    )
    assert error.__cause__ is error.primary_error
    assert isinstance(error.rollback_error, sqlite3.OperationalError)
    assert str(error.rollback_error) == "rollback unavailable"
    assert proxy.rollback_calls == 1

    setattr(backend, "_conn", original)
    original.rollback()
    with backend.transaction():
        col.put("recovered", {"id": "recovered"})
    assert col.get("recovered") is not None


def _create_v1_database(
    db_path: Path, *, payload: dict[str, object] | str
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version (version INTEGER NOT NULL)"
        )
        conn.execute("INSERT INTO _schema_version VALUES (1)")
        for name in COLLECTION_NAMES:
            conn.execute(
                f'CREATE TABLE "col_{name}" '
                "(id TEXT PRIMARY KEY, payload TEXT)"
            )
        wire = payload if isinstance(payload, str) else json.dumps(payload)
        conn.execute(
            "INSERT INTO col_memory_entries (id, payload) VALUES (?, ?)",
            ("mem_legacy", wire),
        )
        conn.commit()
    finally:
        conn.close()


def test_runtime_requires_explicit_v1_migration(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    _create_v1_database(
        db_path,
        payload={"id": "mem_legacy", "title": "Legacy"},
    )
    before = db_path.read_bytes()

    with pytest.raises(
        SqliteStorageUnsupportedVersionError,
        match="requires explicit migration",
    ):
        SqliteStorageBackend(db_path)

    assert db_path.read_bytes() == before
    assert not db_path.with_name("nuself.sqlite.pre-v1-to-v3.bak").exists()


def test_explicit_script_migrates_v1_and_preserves_wire_data(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    wire: dict[str, object] = {
        "id": "mem_legacy",
        "title": "Legacy",
        "confidence": 0.75,
        "tags": ["old", "important"],
        "evidence": {"source": "note"},
    }
    _create_v1_database(db_path, payload=wire)

    dry_run = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "5",
            "--dry-run",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert dry_run.stdout.splitlines() == [
        "upgrade v001_to_v002",
        "upgrade v002_to_v003",
        "upgrade v003_to_v004",
        "upgrade v004_to_v005",
    ]
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "5",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    backend = SqliteStorageBackend(db_path)

    assert backend.collection("memory_entries").get("mem_legacy") == wire
    assert (tmp_path / "nuself.sqlite.pre-v1-to-v5.bak").exists()
    assert backend.collection("memory_entries").get("mem_legacy") == wire
    backend.close()


def test_explicit_script_serializes_concurrent_migration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    _create_v1_database(
        db_path,
        payload={"id": "mem_legacy", "title": "Concurrent"},
    )
    command = [
        sys.executable,
        "-m",
        "scripts.migrate_database",
        str(db_path),
        "--to",
        "3",
    ]

    def run_migration(_: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = tuple(executor.map(run_migration, range(6)))

    assert all(result.returncode == 0 for result in results)
    connection = sqlite3.connect(db_path)
    try:
        versions = tuple(
            row[0]
            for row in connection.execute(
                "SELECT version FROM _schema_version ORDER BY version"
            ).fetchall()
        )
    finally:
        connection.close()
    assert versions == (1, 2, 3)
    assert db_path.with_name("nuself.sqlite.pre-v1-to-v3.bak").is_file()


def test_explicit_script_rejects_incomplete_authority_before_mutation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "not-nuself.sqlite"
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "CREATE TABLE _schema_version (version INTEGER NOT NULL)"
        )
        connection.executemany(
            "INSERT INTO _schema_version VALUES (?)",
            ((1,), (2,)),
        )
        connection.commit()
    finally:
        connection.close()
    before = db_path.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "3",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "missing collection table" in result.stderr
    assert db_path.read_bytes() == before
    assert not db_path.with_name(
        "not-nuself.sqlite.pre-v2-to-v3.bak"
    ).exists()


def test_explicit_script_preserves_external_permissions(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    shared.chmod(0o755)
    db_path = shared / "pack.sqlite"
    _create_v1_database(
        db_path,
        payload={"id": "mem_legacy", "title": "External"},
    )
    db_path.chmod(0o644)
    previous_umask = os.umask(0o022)
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.migrate_database",
                str(db_path),
                "--to",
                "3",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        os.umask(previous_umask)

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(shared.stat().st_mode) == 0o755
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o644
    assert stat.S_IMODE(
        db_path.with_name("pack.sqlite.schema.lock").stat().st_mode
    ) == 0o644
    assert stat.S_IMODE(
        db_path.with_name(
            "pack.sqlite.pre-v1-to-v3.bak"
        ).stat().st_mode
    ) == 0o644


def test_explicit_script_hardens_managed_artifacts(
    tmp_path: Path,
) -> None:
    authority = tmp_path / ".nuself"
    authority.mkdir(mode=0o755)
    db_path = authority / "nuself.sqlite"
    _create_v1_database(
        db_path,
        payload={"id": "mem_legacy", "title": "Managed"},
    )
    db_path.chmod(0o644)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "3",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(authority.stat().st_mode) == 0o700
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(
        db_path.with_name("nuself.sqlite.schema.lock").stat().st_mode
    ) == 0o600
    assert stat.S_IMODE(
        db_path.with_name(
            "nuself.sqlite.pre-v1-to-v3.bak"
        ).stat().st_mode
    ) == 0o600


def test_historical_downgrade_fails_before_mutation(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    backend.close()
    db_path = tmp_path / "nuself.sqlite"
    before = db_path.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "2",
            "--dry-run",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "historical forward-only migration" in result.stderr
    assert db_path.read_bytes() == before
    assert not db_path.with_name("nuself.sqlite.pre-v3-to-v2.bak").exists()


def test_registry_rejects_post_v3_migration_without_downgrade() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from scripts.database_migrations.model import "
                "Migration, validate_registry; "
                "noop=lambda connection: None; "
                "validate_registry(("
                "Migration('one',1,2,noop,None),"
                "Migration('two',2,3,noop,None),"
                "Migration('three',3,4,noop,None)"
                "),current_version=4)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "post-v3 migrations must define downgrade" in result.stderr


def test_v5_migration_round_trip_preserves_records(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    record_id = "mem_round_trip"
    record: dict[str, object] = {
        "id": record_id,
        "title": "Round trip",
        "type": "belief",
        "body": "Preserve this record.",
    }
    backend.collection("memory_entries").put(record_id, record)
    backend.close()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "3",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        connection.close()
    assert "records" not in tables
    assert "workspace_entries" not in tables

    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "5",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    reopened = SqliteStorageBackend(db_path)
    try:
        assert reopened.collection("memory_entries").get(record_id) == record
    finally:
        reopened.close()


def test_v5_schema_has_no_redundant_prefix_indexes(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    backend.close()
    connection = sqlite3.connect(db_path)
    try:
        indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            )
            if isinstance(row[0], str)
        }
    finally:
        connection.close()

    assert "idx_records_collection" not in indexes
    assert "idx_workspace_entries_ns" not in indexes


def test_v4_v5_index_migration_is_reversible(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    backend.close()

    cases: tuple[tuple[str, set[str]], ...] = (
        (
            "4",
            {"idx_records_collection", "idx_workspace_entries_ns"},
        ),
        ("5", set()),
    )
    for target, expected_indexes in cases:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.migrate_database",
                str(db_path),
                "--to",
                target,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        connection = sqlite3.connect(db_path)
        try:
            indexes = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='index' AND sql IS NOT NULL"
                )
                if isinstance(row[0], str)
            }
            assert connection.execute(
                "SELECT MAX(version) FROM _schema_version"
            ).fetchone() == (int(target),)
        finally:
            connection.close()
        assert indexes == expected_indexes


def test_v4_upgrade_compacts_existing_v3_workspace_entries(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    backend.close()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "3",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "CREATE TABLE workspace_entries ("
            "namespace TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
            "PRIMARY KEY(namespace, key))"
        )
        connection.execute(
            "INSERT INTO workspace_entries VALUES (?, ?, ?, ?, ?)",
            (
                "workspace/reason/thread",
                "state",
                '{"value": 1}',
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "4",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT value FROM workspace_entries"
        ).fetchone() == ('{"value":1}',)
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type='table' AND name='workspace_entries'"
        ).fetchone()
    finally:
        connection.close()
    assert table_sql is not None
    assert "WITHOUT ROWID" in table_sql[0]


def test_v5_identity_rejects_named_but_malformed_compact_table(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    backend.close()
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("DROP TABLE records")
        connection.execute(
            "CREATE TABLE records (collection TEXT, id TEXT, payload TEXT)"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        SqliteStorageIdentityError,
        match="not a valid NuSelf authority",
    ):
        SqliteStorageBackend(db_path)


def test_v5_identity_rejects_redundant_secondary_index(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    backend.close()
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "CREATE INDEX redundant_records_collection "
            "ON records(collection)"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        SqliteStorageIdentityError,
        match="not a valid NuSelf authority",
    ):
        SqliteStorageBackend(db_path)


def test_v5_identity_rejects_unversioned_extra_table(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    backend.close()
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("CREATE TABLE unversioned_data (value TEXT)")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(
        SqliteStorageIdentityError,
        match="not a valid NuSelf authority",
    ):
        SqliteStorageBackend(db_path)


def test_v5_wire_payload_does_not_duplicate_record_id(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    record: dict[str, object] = {
        "id": "mem_compact",
        "title": "Stored once",
        "body": "The primary key owns identity.",
    }
    backend.collection("memory_entries").put("mem_compact", record)
    backend.close()
    connection = sqlite3.connect(db_path)
    try:
        row = connection.execute(
            "SELECT id, payload FROM records "
            "WHERE collection='memory_entries'"
        ).fetchone()
    finally:
        connection.close()

    assert row is not None
    assert row[0] == "mem_compact"
    assert json.loads(row[1]) == {
        "title": "Stored once",
        "body": "The primary key owns identity.",
    }


def test_v4_downgrade_requires_workspace_export(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    backend.close()
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO workspace_entries VALUES (?,?,?,?,?)",
            (
                "workspace/reason/thread",
                "state",
                '{"value":1}',
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        connection.commit()
    finally:
        connection.close()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "3",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "must be exported before downgrade" in result.stderr
    connection = sqlite3.connect(db_path)
    try:
        assert connection.execute(
            "SELECT MAX(version) FROM _schema_version"
        ).fetchone() == (5,)
        assert connection.execute(
            "SELECT value FROM workspace_entries"
        ).fetchone() == ('{"value":1}',)
    finally:
        connection.close()


def test_v4_downgrade_failure_rolls_back_all_schema_changes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    backend.close()
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO records VALUES (?,?,?)",
            ("memory_entries", "mem_invalid_column", '{"\\u0000":"value"}'),
        )
        connection.commit()
    finally:
        connection.close()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "3",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    connection = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert connection.execute(
            "SELECT MAX(version) FROM _schema_version"
        ).fetchone() == (5,)
        assert connection.execute(
            "SELECT payload FROM records WHERE id='mem_invalid_column'"
        ).fetchone() == ('{"\\u0000":"value"}',)
    finally:
        connection.close()
    assert "records" in tables
    assert "workspace_entries" in tables
    assert not any(table.startswith("col_") for table in tables)


def test_v5_compact_layout_uses_fewer_pages_than_v3(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    collection = backend.collection("memory_entries")
    with backend.transaction():
        for index in range(400):
            record_id = f"mem_{index:04d}"
            collection.put(
                record_id,
                {
                    "id": record_id,
                    "title": f"Compact record {index}",
                    "body": "repeated-body-" * 20,
                    "tags": ["compact", "schema-v5"],
                },
            )
    backend.close()

    connection = sqlite3.connect(db_path)
    try:
        connection.execute("VACUUM")
        v5_pages = connection.execute("PRAGMA page_count").fetchone()[0]
    finally:
        connection.close()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "3",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("VACUUM")
        v3_pages = connection.execute("PRAGMA page_count").fetchone()[0]
    finally:
        connection.close()

    assert v5_pages < v3_pages


def test_explicit_script_rejects_duplicate_version_history_before_mutation(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "duplicate-history.sqlite"
    _create_v1_database(
        db_path,
        payload={"id": "mem_legacy", "title": "Duplicate"},
    )
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("INSERT INTO _schema_version VALUES (1)")
        connection.commit()
    finally:
        connection.close()
    before = db_path.read_bytes()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "3",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "invalid NuSelf schema version history" in result.stderr
    assert db_path.read_bytes() == before
    assert not db_path.with_name(
        "duplicate-history.sqlite.pre-v1-to-v3.bak"
    ).exists()


def test_explicit_script_rolls_back_invalid_v1_payload(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    _create_v1_database(db_path, payload="not-json")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(db_path),
            "--to",
            "3",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "JSONDecodeError" in result.stderr

    conn = sqlite3.connect(db_path)
    try:
        version = conn.execute(
            "SELECT MAX(version) FROM _schema_version"
        ).fetchone()[0]
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(col_memory_entries)"
            ).fetchall()
        }
    finally:
        conn.close()
    assert version == 1
    assert "payload" in columns


def test_find_filters_work_with_nested(tmp_path: Path) -> None:
    backend = create_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    col = backend.collection("reason_threads")
    col.put("rt_001", {"id": "rt_001", "status": "active", "topic": "Test"})
    col.put("rt_002", {"id": "rt_002", "status": "resolved", "topic": "Done"})

    result = col.find(status="active")
    assert len(result) == 1
    assert result[0]["id"] == "rt_001"
