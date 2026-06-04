"""SQLite-backed storage backend for v0.2.4+.

Every top-level key from the wire dict becomes its own SQL column.
Complex values (list, dict) are stored as JSON text.  All values
round-trip through ``json.dumps/loads`` so types are preserved.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from nuself.storage import COLLECTION_NAMES


def _json(v: object) -> str:
    return json.dumps(v, ensure_ascii=True)


def _from_json(s: str | None) -> object:
    if s is None:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return s


def _collection_table(name: str) -> str:
    return f"col_{name}"


class SqliteCollection:
    """One collection backed by a SQLite table.

    Columns are added dynamically on first ``put()`` for each new key,
    so the schema adapts to whatever data is stored.
    """

    def __init__(self, conn: sqlite3.Connection, table: str, lock: threading.Lock) -> None:
        self._conn = conn
        self._table = table
        self._lock = lock

    def _ensure_columns(self, keys: set[str]) -> None:
        existing = set(self._columns())
        new = [k for k in keys if k not in existing and k != "id"]
        if not new:
            return
        for k in new:
            self._conn.execute(f"ALTER TABLE [{self._table}] ADD COLUMN [{k}] TEXT")

    def _columns(self) -> tuple[str, ...]:
        rows = self._conn.execute(f"PRAGMA table_info([{self._table}])").fetchall()
        return tuple(row[1] for row in rows)

    def get(self, key: str) -> dict[str, object] | None:
        cols = self._columns()
        col_list = ", ".join(f"[{c}]" for c in cols)
        row = self._conn.execute(
            f"SELECT {col_list} FROM [{self._table}] WHERE id = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        result: dict[str, object] = {}
        for i, col in enumerate(cols):
            val = row[i]
            if val is None:
                continue
            if col == "id":
                result[col] = val
            else:
                parsed = _from_json(val)
                if parsed is not None:
                    result[col] = parsed
        return result

    def put(self, key: str, value: dict[str, object]) -> None:
        with self._lock:
            self._ensure_columns(set(value.keys()))
            cols = self._columns()
            write_cols = ["id"] + [c for c in cols if c != "id" and c in value]
            placeholders = ", ".join("?" for _ in write_cols)
            cols_sql = ", ".join(f"[{c}]" for c in write_cols)
            vals = [key] + [_json(value[c]) for c in write_cols if c != "id"]
            self._conn.execute(
                f"INSERT OR REPLACE INTO [{self._table}] ({cols_sql}) VALUES ({placeholders})",
                vals,
            )
            self._conn.commit()

    def delete(self, key: str) -> None:
        with self._lock:
            self._conn.execute(
                f"DELETE FROM [{self._table}] WHERE id = ?", (key,)
            )
            self._conn.commit()

    def list(self) -> tuple[dict[str, object], ...]:
        cols = self._columns()
        if len(cols) <= 1:
            return ()
        col_list = ", ".join(f"[{c}]" for c in cols)
        rows = self._conn.execute(f"SELECT {col_list} FROM [{self._table}]").fetchall()
        items: list[dict[str, object]] = []
        for row in rows:
            d: dict[str, object] = {}
            for i, col in enumerate(cols):
                val = row[i]
                if val is None:
                    continue
                if col == "id":
                    d[col] = val
                else:
                    parsed = _from_json(val)
                    if parsed is not None:
                        d[col] = parsed
            if d:
                items.append(d)
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


class SqliteStorageBackend:
    """Storage backend backed by a single SQLite database file."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._lock = threading.Lock()
        self._closed = False
        self._init_schema()

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
            self._apply_v2()
            self._conn.execute("INSERT INTO _schema_version (version) VALUES (2)")
            self._conn.commit()

    def _apply_v1(self) -> None:
        for name in COLLECTION_NAMES:
            table = _collection_table(name)
            self._conn.execute(f"CREATE TABLE IF NOT EXISTS [{table}] (id TEXT PRIMARY KEY)")
        self._conn.commit()

    def _apply_v2(self) -> None:
        # v2 uses dynamic columns — no payload column.
        # Any existing tables from v1 already have id + payload.
        # We drop the payload column so dynamic columns take over.
        for name in COLLECTION_NAMES:
            table = _collection_table(name)
            info = self._conn.execute(f"PRAGMA table_info([{table}])").fetchall()
            col_names = [r[1] for r in info]
            if "payload" in col_names:
                self._conn.execute(
                    f"ALTER TABLE [{table}] DROP COLUMN payload"
                )
        self._conn.commit()

    def collection(self, name: str) -> SqliteCollection:
        table = _collection_table(name)
        _verify_table(self._conn, table, name)
        return SqliteCollection(self._conn, table, self._lock)

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
        rows = self._conn.execute(f"PRAGMA table_info([{table}])").fetchall()
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
