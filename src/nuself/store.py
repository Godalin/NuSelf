"""General-purpose sync SQLite key-value store, implementing LangGraph's BaseStore.

Any agent can use ``SqliteStore`` for persistent JSON document storage,
and ``ScopedWorkspace`` to auto-inject a namespace prefix (e.g. a thread ID)
so the agent does not need to manage namespaces manually.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, cast

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

from nuself.private_fs import require_private_file
from nuself.runtime.messages import decode_json_value, encode_json_value

__all__ = [
    "SqliteStore",
    "SqliteStoreLifecycleError",
    "ScopedWorkspace",
    "WorkspaceCollection",
]

class SqliteStoreLifecycleError(RuntimeError):
    """Retain transaction and connection cleanup failures."""

    def __init__(
        self,
        *,
        primary_error: BaseException | None,
        rollback_error: BaseException | None,
        close_error: BaseException | None,
    ) -> None:
        super().__init__(
            "workspace SQLite transaction lifecycle failed"
            if primary_error is not None
            else "workspace SQLite connection could not be closed"
        )
        self.primary_error = primary_error
        self.rollback_error = rollback_error
        self.close_error = close_error


def _run_transaction[_T](
    db_path: Path,
    operation: Callable[[sqlite3.Connection], _T],
) -> _T:
    conn = sqlite3.connect(str(db_path))
    try:
        result = operation(conn)
        conn.commit()
    except BaseException as primary_error:
        rollback_error: BaseException | None = None
        try:
            conn.rollback()
        except BaseException as error:
            rollback_error = error
        try:
            conn.close()
        except BaseException as close_error:
            raise SqliteStoreLifecycleError(
                primary_error=primary_error,
                rollback_error=rollback_error,
                close_error=close_error,
            ) from primary_error
        if rollback_error is not None:
            raise SqliteStoreLifecycleError(
                primary_error=primary_error,
                rollback_error=rollback_error,
                close_error=None,
            ) from primary_error
        raise
    try:
        conn.close()
    except BaseException as close_error:
        raise SqliteStoreLifecycleError(
            primary_error=None,
            rollback_error=None,
            close_error=close_error,
        ) from close_error
    return result


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
        require_private_file(db_path)
        connection = sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)
        try:
            row = connection.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type='table' AND name='workspace_entries'"
            ).fetchone()
            if row is None:
                raise ValueError(
                    "workspace_entries requires explicit schema migration"
                )
        finally:
            connection.close()

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        def execute(conn: sqlite3.Connection) -> list[Result]:
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
            return results

        return _run_transaction(self._db_path, execute)

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
            value=cast(dict[str, Any], decode_json_value(row[0])),
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
        encoded_value = encode_json_value(
            op.value,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        existing = conn.execute(
            "SELECT created_at FROM workspace_entries WHERE namespace = ? AND key = ?",
            (nskey, op.key),
        ).fetchone()
        if existing is not None:
            conn.execute(
                "UPDATE workspace_entries SET value = ?, updated_at = ? WHERE namespace = ? AND key = ?",
                (encoded_value, now, nskey, op.key),
            )
        else:
            conn.execute(
                "INSERT INTO workspace_entries (namespace, key, value, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (nskey, op.key, encoded_value, now, now),
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
                value=cast(dict[str, Any], decode_json_value(row[0])),
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
        sub: str | None = None,
    ) -> list[dict[str, Any]]:
        prefix = self._prefix + ((sub,) if sub else ())
        items = self._store.search(prefix, query=query, filter=filter, limit=limit, offset=offset)
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


class WorkspaceCollection:
    """Expose one scoped workspace namespace as a storage collection."""

    def __init__(self, workspace: ScopedWorkspace, *, namespace: str) -> None:
        if not namespace:
            raise ValueError("workspace collection namespace must not be empty")
        self._workspace = workspace
        self._namespace = namespace

    def get(self, key: str) -> dict[str, object] | None:
        return cast(
            dict[str, object] | None,
            self._workspace.get(key, sub=self._namespace),
        )

    def put(self, key: str, value: dict[str, object]) -> None:
        self._workspace.put(key, cast(dict[str, Any], value), sub=self._namespace)

    def delete(self, key: str) -> None:
        self._workspace.delete(key, sub=self._namespace)

    def list(self) -> tuple[dict[str, object], ...]:
        return tuple(
            cast(
                list[dict[str, object]],
                self._workspace.search(limit=10_000, sub=self._namespace),
            )
        )

    def find(self, **filters: object) -> tuple[dict[str, object], ...]:
        return tuple(
            cast(
                list[dict[str, object]],
                self._workspace.search(
                    filter=cast(dict[str, Any], filters),
                    limit=10_000,
                    sub=self._namespace,
                ),
            )
        )
