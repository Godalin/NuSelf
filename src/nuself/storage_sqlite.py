"""SQLite-backed storage backend for v0.2.4+.

Every top-level key from the wire dict becomes its own SQL column.
Complex values (list, dict) are stored as JSON text.  All values
round-trip through ``json.dumps/loads`` so types are preserved.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol, cast

from nuself.logs import LogComponent
from nuself.runtime.observability import report_corrupt_record
from nuself.storage import (
    COLLECTION_LOG_COMPONENTS,
    COLLECTION_NAMES,
)


def _json(v: object) -> str:
    return json.dumps(v, ensure_ascii=True)


def _from_json(value: str) -> object:
    return json.loads(value)


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


class SqliteTransactionError(RuntimeError):
    """Base class for SQLite transaction-state failures."""


class SqliteTransactionRollbackOnlyError(SqliteTransactionError):
    """Raised when a caught inner failure prevents the outer commit."""


class SqliteTransactionCleanupError(SqliteTransactionError):
    """Raised when rollback fails while preserving the primary cause."""


class _Lock(Protocol):
    def acquire(self) -> bool: ...
    def release(self) -> None: ...


class SqliteCollection:
    """One collection backed by a SQLite table.

    Columns are added dynamically on first ``put()`` for each new key,
    so the schema adapts to whatever data is stored.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        table: str,
        lock: _Lock,
        column_cache: dict[str, tuple[str, ...]],
        transaction_state: _TransactionState,
        *,
        collection_name: str,
        component: LogComponent,
        project_root: Path,
    ) -> None:
        self._conn = conn
        self._table = table
        self._lock = lock
        # Shared across every collection object for this table (they share the
        # backend connection), so an ALTER by one is seen by all.
        self._column_cache = column_cache
        self._transaction_state = transaction_state
        self._collection_name = collection_name
        self._component: LogComponent = component
        self._project_root = project_root

    def _ensure_columns(self, keys: set[str]) -> None:
        existing = set(self._columns())
        new = [k for k in keys if k not in existing and k != "id"]
        if not new:
            return
        for k in new:
            self._conn.execute(
                f"ALTER TABLE {_identifier(self._table)} "
                f"ADD COLUMN {_identifier(k)} TEXT"
            )
        # Invalidate so the next _columns() re-reads the widened schema.
        self._column_cache.pop(self._table, None)

    def _columns(self) -> tuple[str, ...]:
        cached = self._column_cache.get(self._table)
        if cached is not None:
            return cached
        rows = self._conn.execute(
            f"PRAGMA table_info({_identifier(self._table)})"
        ).fetchall()
        cols = tuple(row[1] for row in rows)
        self._column_cache[self._table] = cols
        return cols

    def _row_to_dict(self, cols: tuple[str, ...], row: tuple[object, ...]) -> dict[str, object]:
        result: dict[str, object] = {}
        for i, col in enumerate(cols):
            val = row[i]
            if val is None:
                continue
            if col == "id":
                if not isinstance(val, str) or not val:
                    raise ValueError("stored SQLite row id is invalid")
                result[col] = val
            else:
                if not isinstance(val, str):
                    raise ValueError(
                        "stored SQLite dynamic column is not JSON text"
                    )
                try:
                    parsed = _from_json(val)
                except (json.JSONDecodeError, ValueError) as exc:
                    raise ValueError(
                        "stored SQLite dynamic column is invalid JSON"
                    ) from exc
                result[col] = parsed
        return result

    def _decode_list_rows(
        self,
        cols: tuple[str, ...],
        rows: list[tuple[object, ...]],
    ) -> tuple[dict[str, object], ...]:
        items: list[dict[str, object]] = []
        for row in rows:
            try:
                item = self._row_to_dict(cols, row)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                report_corrupt_record(
                    exc,
                    component=self._component,
                    collection=self._collection_name,
                    record_id=_row_record_id(cols, row),
                    project_root=self._project_root,
                )
                continue
            if item:
                items.append(item)
        return tuple(items)

    def get(self, key: str) -> dict[str, object] | None:
        cols = self._columns()
        col_list = ", ".join(_identifier(c) for c in cols)
        row = self._conn.execute(
            f"SELECT {col_list} FROM {_identifier(self._table)} WHERE id = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(cols, row)

    def put(self, key: str, value: dict[str, object]) -> None:
        self._lock.acquire()
        try:
            self._ensure_columns(set(value.keys()))
            cols = self._columns()
            # put() replaces the complete wire object. Include every known
            # column so fields omitted by the replacement become SQL NULL.
            write_cols = ["id"] + [c for c in cols if c != "id"]
            placeholders = ", ".join("?" for _ in write_cols)
            cols_sql = ", ".join(_identifier(c) for c in write_cols)
            vals = [key] + [
                _json(value[c]) if c in value else None
                for c in write_cols
                if c != "id"
            ]
            update_cols = [c for c in write_cols if c != "id"]
            if update_cols:
                updates = ", ".join(
                    f"{_identifier(c)} = excluded.{_identifier(c)}"
                    for c in update_cols
                )
                conflict = f" DO UPDATE SET {updates}"
            else:
                conflict = " DO NOTHING"
            self._conn.execute(
                f"INSERT INTO {_identifier(self._table)} ({cols_sql}) "
                f"VALUES ({placeholders}) ON CONFLICT(id){conflict}",
                vals,
            )
            self._commit_if_standalone()
        finally:
            self._lock.release()

    def delete(self, key: str) -> None:
        self._lock.acquire()
        try:
            self._conn.execute(
                f"DELETE FROM {_identifier(self._table)} WHERE id = ?", (key,)
            )
            self._commit_if_standalone()
        finally:
            self._lock.release()

    def _commit_if_standalone(self) -> None:
        if self._transaction_state.depth == 0:
            self._conn.commit()

    def list(self) -> tuple[dict[str, object], ...]:
        cols = self._columns()
        if len(cols) <= 1:
            return ()
        col_list = ", ".join(_identifier(c) for c in cols)
        rows = self._conn.execute(
            f"SELECT {col_list} FROM {_identifier(self._table)}"
        ).fetchall()
        return self._decode_list_rows(cols, rows)

    def find(self, **filters: object) -> tuple[dict[str, object], ...]:
        if not filters:
            return self.list()
        cols = self._columns()
        if len(cols) <= 1:
            return ()
        colset = set(cols)
        # None filters keep the original Python-side comparison semantics (a stored
        # null round-trips to an absent key), so only push non-None filters to SQL.
        if any(expected is None for expected in filters.values()):
            return tuple(
                item
                for item in self.list()
                if all(item.get(key) == expected for key, expected in filters.items())
            )
        where_parts: list[str] = []
        params: list[object] = []
        for key, expected in filters.items():
            if key not in colset:
                # Filtering on a column that does not exist matches nothing.
                return ()
            where_parts.append(f"{_identifier(key)} = ?")
            # id is stored raw; every other value is stored as JSON text.
            params.append(expected if key == "id" else _json(expected))
        col_list = ", ".join(_identifier(c) for c in cols)
        sql = (
            f"SELECT {col_list} FROM {_identifier(self._table)} WHERE "
            + " AND ".join(where_parts)
        )
        rows = self._conn.execute(sql, params).fetchall()
        return self._decode_list_rows(cols, rows)


class SqliteStorageBackend:
    """Storage backend backed by a single SQLite database file."""

    def __init__(
        self,
        db_path: Path,
        *,
        project_root: Path | None = None,
    ) -> None:
        self._db_path = db_path
        self._project_root = (
            project_root
            if project_root is not None
            else (
                db_path.parent.parent
                if db_path.parent.name == "private"
                else db_path.parent
            )
        )
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = threading.RLock()
        self._transaction_state = _TransactionState()
        self._closed = False
        # Per-table column cache shared by all SqliteCollection objects, so a
        # dynamic ALTER by one collection is visible to the others.
        self._column_cache: dict[str, tuple[str, ...]] = {}
        try:
            self._init_schema()
        except Exception:
            self._conn.close()
            self._closed = True
            raise

    @property
    def db_path(self) -> Path:
        return self._db_path

    def close(self) -> None:
        """Close the database connection, checkpointing WAL first."""
        if self._closed:
            return
        self._closed = True
        try:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except sqlite3.Error:
            pass
        try:
            self._conn.close()
        except sqlite3.Error:
            pass

    def _init_schema(self) -> None:
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS _schema_version (version INTEGER NOT NULL)"
        )
        (current_version,) = self._conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM _schema_version"
        ).fetchone()
        if current_version < 1:
            self._apply_v1()
            self._conn.execute("INSERT INTO _schema_version (version) VALUES (1)")
            self._conn.commit()
        if current_version < 2:
            self._backup_before_v2_if_needed()
            with self.transaction():
                self._apply_v2()
                self._conn.execute(
                    "INSERT INTO _schema_version (version) VALUES (2)"
                )

    def _apply_v1(self) -> None:
        for name in COLLECTION_NAMES:
            table = _collection_table(name)
            self._conn.execute(
                f"CREATE TABLE IF NOT EXISTS {_identifier(table)} "
                "(id TEXT PRIMARY KEY)"
            )
        self._conn.commit()

    def _apply_v2(self) -> None:
        """Expand a legacy v1 payload object into v2 dynamic columns."""
        for name in COLLECTION_NAMES:
            table = _collection_table(name)
            info = self._conn.execute(
                f"PRAGMA table_info({_identifier(table)})"
            ).fetchall()
            col_names = [r[1] for r in info]
            if "payload" in col_names:
                rows = self._conn.execute(
                    f"SELECT id, payload FROM {_identifier(table)}"
                ).fetchall()
                payloads: list[tuple[str, dict[str, object]]] = []
                keys: set[str] = set()
                for row_id, payload_text in rows:
                    if not isinstance(row_id, str) or not isinstance(payload_text, str):
                        raise ValueError(f"invalid v1 row in collection {name!r}")
                    parsed: object = json.loads(payload_text)
                    if not isinstance(parsed, dict):
                        raise ValueError(
                            f"invalid v1 payload in collection {name!r}: expected object"
                        )
                    parsed_dict = cast(dict[object, object], parsed)
                    payload: dict[str, object] = {
                        str(key): value for key, value in parsed_dict.items()
                    }
                    payload_id = payload.get("id")
                    if payload_id is not None and payload_id != row_id:
                        raise ValueError(
                            f"v1 payload id mismatch in collection {name!r}: {row_id!r}"
                        )
                    payload["id"] = row_id
                    payloads.append((row_id, payload))
                    keys.update(key for key in payload if key != "id")
                for key in sorted(keys):
                    if key not in col_names:
                        self._conn.execute(
                            f"ALTER TABLE {_identifier(table)} "
                            f"ADD COLUMN {_identifier(key)} TEXT"
                        )
                for row_id, payload in payloads:
                    for key, value in payload.items():
                        if key == "id":
                            continue
                        self._conn.execute(
                            f"UPDATE {_identifier(table)} "
                            f"SET {_identifier(key)} = ? WHERE id = ?",
                            (_json(value), row_id),
                        )
                self._conn.execute(
                    f"ALTER TABLE {_identifier(table)} DROP COLUMN payload"
                )
        self._column_cache.clear()

    def _backup_before_v2_if_needed(self) -> None:
        has_payload = False
        for name in COLLECTION_NAMES:
            table = _collection_table(name)
            info = self._conn.execute(
                f"PRAGMA table_info({_identifier(table)})"
            ).fetchall()
            if any(row[1] == "payload" for row in info):
                has_payload = True
                break
        if not has_payload:
            return
        backup_path = self._db_path.with_name(f"{self._db_path.name}.v1.bak")
        backup = sqlite3.connect(str(backup_path))
        try:
            self._conn.backup(backup)
        finally:
            backup.close()

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
            self._column_cache.clear()
            self._reset_transaction_state()
            raise SqliteTransactionCleanupError(
                "SQLite rollback failed after "
                f"{type(primary_error).__name__}: {rollback_error}"
            ) from primary_error
        self._column_cache.clear()
        self._reset_transaction_state()

    def _reset_transaction_state(self) -> None:
        self._transaction_state.depth = 0
        self._transaction_state.rollback_only = False

    def collection(self, name: str) -> SqliteCollection:
        table = _collection_table(name)
        _verify_table(self._conn, table, name)
        return SqliteCollection(
            self._conn,
            table,
            self._lock,
            self._column_cache,
            self._transaction_state,
            collection_name=name,
            component=COLLECTION_LOG_COMPONENTS[name],
            project_root=self._project_root,
        )

    def collection_names(self) -> tuple[str, ...]:
        result: list[str] = []
        for name in COLLECTION_NAMES:
            table = _collection_table(name)
            row = self._conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table,),
            ).fetchone()
            if row is not None:
                result.append(name)
        return tuple(result)

    def table_info(self, name: str) -> list[tuple[str, str, bool, str | None, bool]]:
        table = _collection_table(name)
        rows = self._conn.execute(
            f"PRAGMA table_info({_identifier(table)})"
        ).fetchall()
        return [
            (row[1], row[2], bool(row[3]), row[4], bool(row[5]))
            for row in rows
        ]


def _verify_table(conn: sqlite3.Connection, table: str, name: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    if row is None:
        raise ValueError(f"unknown collection: {name!r}")


def _row_record_id(
    cols: tuple[str, ...],
    row: tuple[object, ...],
) -> str:
    try:
        index = cols.index("id")
        value = row[index]
    except (ValueError, IndexError):
        return "<unknown>"
    return value if isinstance(value, str) and value else "<unknown>"
