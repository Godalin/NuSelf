"""Tests for SqliteStorageBackend and SqliteCollection."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import cast

import pytest

from nuself.logs import read_log_events
from nuself.storage import (
    DefaultBackendResetError,
    StorageBackend,
    create_sqlite_backend,
    get_default_backend,
    reset_default_backend,
    set_default_backend,
)
from nuself.storage_sqlite import (
    COLLECTION_NAMES,
    SqliteStorageBackend,
    SqliteStorageCheckpointError,
    SqliteStorageCloseError,
    SqliteStorageInitializationCleanupError,
    SqliteTransactionCleanupError,
    SqliteTransactionRollbackOnlyError,
)


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
        conn.execute(
            f'UPDATE "{table}" SET "{column}" = ? WHERE id = ?',
            (value, record_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_create_sqlite_backend_creates_db(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    backend = create_sqlite_backend(db_path=db_path)
    assert isinstance(backend, SqliteStorageBackend)
    assert db_path.exists()


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


def test_close_is_idempotent_after_connection_closes(
    tmp_path: Path,
) -> None:
    backend = SqliteStorageBackend(tmp_path / "nuself.sqlite")
    original = cast(sqlite3.Connection, getattr(backend, "_conn"))
    proxy = LifecycleConnectionProxy(original)
    setattr(backend, "_conn", cast(sqlite3.Connection, proxy))

    backend.close()
    backend.close()

    assert proxy.checkpoint_calls == 1
    assert proxy.close_calls == 1


def test_checkpoint_failure_is_raised_after_connection_closes(
    tmp_path: Path,
) -> None:
    backend = SqliteStorageBackend(tmp_path / "nuself.sqlite")
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
    backend = SqliteStorageBackend(tmp_path / "nuself.sqlite")
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
    backend = SqliteStorageBackend(tmp_path / "nuself.sqlite")
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
    backend = SqliteStorageBackend(tmp_path / "nuself.sqlite")
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
        SqliteStorageBackend(tmp_path / "nuself.sqlite")

    assert isinstance(captured.value.__cause__, sqlite3.OperationalError)
    assert str(captured.value.__cause__) == "schema init unavailable"
    assert isinstance(
        captured.value.cleanup_error,
        sqlite3.OperationalError,
    )
    assert str(captured.value.cleanup_error) == "close unavailable"
    proxy.fail_close = False
    proxy.close()


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
        match="dynamic column is invalid JSON",
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
        match="dynamic column is not JSON text",
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

    backend2 = create_sqlite_backend(db_path=db_path)
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


def test_transaction_rolls_back_all_collection_writes(tmp_path: Path) -> None:
    backend = SqliteStorageBackend(tmp_path / "nuself.sqlite")
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
    backend = SqliteStorageBackend(tmp_path / "nuself.sqlite")
    col = backend.collection("memory_entries")
    with backend.transaction():
        col.put("a", {"id": "a", "value": 1})
        with backend.transaction():
            col.put("b", {"id": "b", "value": 2})
    assert {item["id"] for item in col.list()} == {"a", "b"}


def test_caught_nested_failure_makes_outer_transaction_rollback_only(
    tmp_path: Path,
) -> None:
    backend = SqliteStorageBackend(tmp_path / "nuself.sqlite")
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
    backend = SqliteStorageBackend(tmp_path / "nuself.sqlite")
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
    backend = SqliteStorageBackend(tmp_path / "nuself.sqlite")
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
    backend = SqliteStorageBackend(tmp_path / "nuself.sqlite")
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
    assert proxy.rollback_calls == 1

    setattr(backend, "_conn", original)
    original.rollback()


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


def test_v1_payload_migration_preserves_complete_wire_data(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    wire: dict[str, object] = {
        "id": "mem_legacy",
        "title": "Legacy",
        "confidence": 0.75,
        "tags": ["old", "important"],
        "evidence": {"source": "note"},
    }
    _create_v1_database(db_path, payload=wire)

    backend = SqliteStorageBackend(db_path)

    assert backend.collection("memory_entries").get("mem_legacy") == wire
    assert (tmp_path / "nuself.sqlite.v1.bak").exists()
    assert "payload" not in {
        column[0] for column in backend.table_info("memory_entries")
    }


def test_invalid_v1_payload_rolls_back_schema_upgrade(tmp_path: Path) -> None:
    db_path = tmp_path / "nuself.sqlite"
    _create_v1_database(db_path, payload="not-json")

    with pytest.raises(json.JSONDecodeError):
        SqliteStorageBackend(db_path)

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
