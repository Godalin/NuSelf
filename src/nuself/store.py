"""General-purpose sync SQLite key-value store, implementing LangGraph's BaseStore.

Any agent can use ``SqliteStore`` for persistent JSON document storage,
and ``ScopedWorkspace`` to auto-inject a namespace prefix (e.g. a thread ID)
so the agent does not need to manage namespaces manually.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, cast

from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    ListNamespacesOp,
    Op,
    PutOp,
    Result,
    SearchItem,
    SearchOp,
)

from nuself.config import runtime_paths

__all__ = [
    "SqliteStore",
    "ScopedWorkspace",
]


def _create_workspace_entries_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_entries (
            namespace TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (namespace, key)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workspace_entries_ns ON workspace_entries(namespace)"
    )


class SqliteStore(BaseStore):
    """Sync SQLite-backed ``BaseStore`` for persistent JSON document storage.

    Each value is stored as a JSON blob keyed by ``(namespace, key)``.

    Usage::

        store = SqliteStore(Path("/path/to/workspace.sqlite"))
        store.put(("my_namespace",), "my_key", {"hello": "world"})
        item = store.get(("my_namespace",), "my_key")
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            _create_workspace_entries_table(conn)
            conn.commit()
        finally:
            conn.close()

    @classmethod
    def for_project(
        cls,
        project_root: Path | None = None,
        *,
        db_path: Path | None = None,
    ) -> SqliteStore:
        """Create a ``SqliteStore`` backed by the main project database."""
        path = db_path if db_path is not None else runtime_paths(project_root).private_root / "nuself.sqlite"
        return cls(path)

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        conn = sqlite3.connect(str(self._db_path))
        try:
            results: list[Result] = []
            for op in ops:
                if isinstance(op, GetOp):
                    results.append(self._do_get(conn, op))
                elif isinstance(op, PutOp):
                    results.append(self._do_put(conn, op))
                elif isinstance(op, SearchOp):
                    results.append(self._do_search(conn, op))
                else:
                    results.append(self._do_list_namespaces(conn, op))
            conn.commit()
            return results
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        return self.batch(ops)

    # ── Internal ────────────────────────────────────────────────────

    @staticmethod
    def _ns_key(namespace: tuple[str, ...]) -> str:
        return "/".join(namespace)

    def _do_get(self, conn: sqlite3.Connection, op: GetOp) -> Item | None:
        nskey = self._ns_key(op.namespace)
        row = conn.execute(
            "SELECT value, key, namespace, created_at, updated_at FROM workspace_entries WHERE namespace = ? AND key = ?",
            (nskey, op.key),
        ).fetchone()
        if row is None:
            return None
        return Item(
            value=cast(dict[str, Any], json.loads(row[0])),
            key=row[1],
            namespace=tuple(row[2].split("/")) if row[2] else (),
            created_at=row[3],
            updated_at=row[4],
        )

    def _do_put(self, conn: sqlite3.Connection, op: PutOp) -> None:
        if op.value is None:
            nskey = self._ns_key(op.namespace)
            conn.execute(
                "DELETE FROM workspace_entries WHERE namespace = ? AND key = ?",
                (nskey, op.key),
            )
            return
        now = datetime.now(UTC).isoformat()
        nskey = self._ns_key(op.namespace)
        existing = conn.execute(
            "SELECT created_at FROM workspace_entries WHERE namespace = ? AND key = ?",
            (nskey, op.key),
        ).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE workspace_entries SET value = ?, updated_at = ? WHERE namespace = ? AND key = ?",
                (json.dumps(op.value, ensure_ascii=True), now, nskey, op.key),
            )
        else:
            conn.execute(
                "INSERT INTO workspace_entries (namespace, key, value, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (nskey, op.key, json.dumps(op.value, ensure_ascii=True), now, now),
            )

    def _do_search(self, conn: sqlite3.Connection, op: SearchOp) -> list[SearchItem]:
        prefix = self._ns_key(op.namespace_prefix)
        like = prefix + "%" if prefix else "%"
        params: list[Any] = [like]
        sql = "SELECT value, key, namespace, created_at, updated_at FROM workspace_entries WHERE namespace LIKE ?"
        if op.filter:
            for fk, fv in op.filter.items():
                sql += f" AND json_extract(value, '$.{fk}') = ?"
                params.append(fv)
        sql += " ORDER BY created_at ASC LIMIT ? OFFSET ?"
        params.extend([op.limit, op.offset])
        rows = conn.execute(sql, params).fetchall()
        return [
            SearchItem(
                value=cast(dict[str, Any], json.loads(row[0])),
                key=row[1],
                namespace=tuple(row[2].split("/")) if row[2] else (),
                created_at=row[3],
                updated_at=row[4],
                score=0.0,
            )
            for row in rows
        ]

    def _do_list_namespaces(self, conn: sqlite3.Connection, op: ListNamespacesOp) -> list[tuple[str, ...]]:
        sql = "SELECT DISTINCT namespace FROM workspace_entries"
        conditions: list[str] = []
        params: list[Any] = []
        match_conditions = op.match_conditions
        if match_conditions:
            for mc in match_conditions:
                if mc.match_type == "prefix":
                    conditions.append("namespace LIKE ?")
                    params.append(self._ns_key(mc.path) + "%")
                elif mc.match_type == "suffix":
                    conditions.append("namespace LIKE ?")
                    params.append("%" + self._ns_key(mc.path))
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY namespace ASC LIMIT ? OFFSET ?"
        params.extend([op.limit, op.offset])
        rows = conn.execute(sql, params).fetchall()
        result: list[tuple[str, ...]] = []
        for (ns,) in rows:
            parts = tuple(ns.split("/")) if ns else ()
            if op.max_depth is not None and len(parts) > op.max_depth:
                parts = parts[: op.max_depth]
            result.append(parts)
        return result


class ScopedWorkspace:
    """Namespace-scoped wrapper around a ``SqliteStore``.

    Auto-injects a fixed prefix (e.g. a thread ID) into every operation,
    so the caller does not need to manage namespaces manually.

    Usage::

        store = SqliteStore(Path("/path/to/workspace.sqlite"))
        ws = ScopedWorkspace(store, ("thread_123",))
        ws.put("my_key", {"answer": 42})           # → store.put(("thread_123",), "my_key", ...)
        item = ws.get("my_key", sub="branch_a")     # → store.get(("thread_123", "branch_a"), "my_key")
    """

    def __init__(self, store: SqliteStore, namespace_prefix: tuple[str, ...]) -> None:
        self._store = store
        self._prefix = namespace_prefix

    def put(self, key: str, value: dict[str, Any], *, sub: str | None = None) -> None:
        ns = self._prefix + ((sub,) if sub else ())
        self._store.put(ns, key, value)

    def get(self, key: str, *, sub: str | None = None) -> dict[str, Any] | None:
        ns = self._prefix + ((sub,) if sub else ())
        item = self._store.get(ns, key)
        return item.value if item is not None else None

    def search(
        self,
        *,
        query: str | None = None,
        filter: dict[str, Any] | None = None,
        limit: int = 10,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        items = self._store.search(self._prefix, query=query, filter=filter, limit=limit, offset=offset)
        return [item.value for item in items]

    def delete(self, key: str, *, sub: str | None = None) -> None:
        ns = self._prefix + ((sub,) if sub else ())
        self._store.delete(ns, key)

    def list_namespaces(
        self,
        *,
        max_depth: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[tuple[str, ...]]:
        return self._store.list_namespaces(prefix=self._prefix, max_depth=max_depth, limit=limit, offset=offset)



