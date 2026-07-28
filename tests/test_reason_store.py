"""Tests for ReasonStore and ReasonWorkspace."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Callable, cast

import pytest
from langgraph.store.base import PutOp

from nuself.store import (
    ScopedWorkspace,
    SqliteStore,
    SqliteStoreLifecycleError,
)
from nuself.workspace import PrivateWorkspacePaths


def _paths(tmp_path: Path) -> PrivateWorkspacePaths:
    root = tmp_path / "ws"
    return PrivateWorkspacePaths(
        root=root,
        database=root / "workspace.sqlite",
        artifacts=root / "artifacts",
        notes=root / "notes",
    )


def _db(tmp_path: Path) -> Path:
    return _paths(tmp_path).database


class LifecycleConnectionProxy:
    def __init__(
        self,
        delegate: sqlite3.Connection,
        *,
        fail_commit: bool = False,
        fail_rollback: bool = False,
        fail_close: bool = False,
    ) -> None:
        self._delegate = delegate
        self.fail_commit = fail_commit
        self.fail_rollback = fail_rollback
        self.fail_close = fail_close
        self.close_calls = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def commit(self) -> None:
        if self.fail_commit:
            raise RuntimeError("commit failed")
        self._delegate.commit()

    def rollback(self) -> None:
        if self.fail_rollback:
            raise RuntimeError("rollback failed")
        self._delegate.rollback()

    def close(self) -> None:
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError("close failed")
        self._delegate.close()


def _connection_factory(
    connection: LifecycleConnectionProxy,
) -> Callable[[str], sqlite3.Connection]:
    def connect(database: str) -> sqlite3.Connection:
        del database
        return cast(sqlite3.Connection, connection)

    return connect


def test_store_put_and_get(tmp_path: Path) -> None:
    store = SqliteStore(_db(tmp_path))
    store.put(("thread",), "key1", {"msg": "hello"})
    item = store.get(("thread",), "key1")
    assert item is not None
    assert item.value == {"msg": "hello"}
    assert item.key == "key1"
    assert item.namespace == ("thread",)


def test_store_get_missing(tmp_path: Path) -> None:
    store = SqliteStore(_db(tmp_path))
    assert store.get(("ns",), "missing") is None


def test_store_put_overwrites(tmp_path: Path) -> None:
    store = SqliteStore(_db(tmp_path))
    store.put(("ns",), "k", {"v": 1})
    store.put(("ns",), "k", {"v": 2})
    item = store.get(("ns",), "k")
    assert item is not None
    assert item.value == {"v": 2}


def test_store_batch_rolls_back_when_later_value_is_not_strict_json(
    tmp_path: Path,
) -> None:
    store = SqliteStore(_db(tmp_path))
    store.put(("ns",), "existing", {"value": "old"})

    with pytest.raises(TypeError, match="floats must be finite"):
        store.batch(
            [
                PutOp(("ns",), "new", {"value": "written first"}),
                PutOp(("ns",), "existing", {"value": float("-inf")}),
            ]
        )

    assert store.get(("ns",), "new") is None
    existing = store.get(("ns",), "existing")
    assert existing is not None
    assert existing.value == {"value": "old"}


def test_store_batch_retains_primary_rollback_and_close_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SqliteStore(_db(tmp_path))
    raw = sqlite3.connect(_db(tmp_path))
    connection = LifecycleConnectionProxy(
        raw,
        fail_rollback=True,
        fail_close=True,
    )
    monkeypatch.setattr(
        "nuself.store.sqlite3.connect",
        _connection_factory(connection),
    )

    try:
        with pytest.raises(SqliteStoreLifecycleError) as captured:
            store.put(("ns",), "invalid", {"value": float("inf")})
    finally:
        raw.close()

    assert isinstance(captured.value.primary_error, TypeError)
    assert isinstance(captured.value.rollback_error, RuntimeError)
    assert isinstance(captured.value.close_error, RuntimeError)
    assert captured.value.__cause__ is captured.value.primary_error
    assert connection.close_calls == 1


def test_store_commit_failure_propagates_after_successful_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SqliteStore(_db(tmp_path))
    raw = sqlite3.connect(_db(tmp_path))
    connection = LifecycleConnectionProxy(raw, fail_commit=True)
    monkeypatch.setattr(
        "nuself.store.sqlite3.connect",
        _connection_factory(connection),
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        store.put(("ns",), "key", {"value": "not committed"})

    assert connection.close_calls == 1


def test_store_surfaces_close_failure_after_successful_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SqliteStore(_db(tmp_path))
    raw = sqlite3.connect(_db(tmp_path))
    connection = LifecycleConnectionProxy(raw, fail_close=True)
    monkeypatch.setattr(
        "nuself.store.sqlite3.connect",
        _connection_factory(connection),
    )

    try:
        with pytest.raises(SqliteStoreLifecycleError) as captured:
            store.put(("ns",), "key", {"value": "committed"})
    finally:
        raw.close()

    assert captured.value.primary_error is None
    assert captured.value.rollback_error is None
    assert isinstance(captured.value.close_error, RuntimeError)
    assert captured.value.__cause__ is captured.value.close_error
    assert connection.close_calls == 1


def test_store_delete(tmp_path: Path) -> None:
    store = SqliteStore(_db(tmp_path))
    store.put(("ns",), "k", {"v": 1})
    store.delete(("ns",), "k")
    assert store.get(("ns",), "k") is None


def test_store_search_all(tmp_path: Path) -> None:
    store = SqliteStore(_db(tmp_path))
    store.put(("t", "branch_a"), "k1", {"score": 1})
    store.put(("t", "branch_b"), "k2", {"score": 2})
    results = store.search(("t",), limit=10)
    assert len(results) == 2


def test_store_search_with_filter(tmp_path: Path) -> None:
    store = SqliteStore(_db(tmp_path))
    store.put(("t",), "a", {"type": "hypothesis", "text": "h1"})
    store.put(("t",), "b", {"type": "evidence", "text": "e1"})
    results = store.search(("t",), filter={"type": "hypothesis"})
    assert len(results) == 1
    assert results[0].value["text"] == "h1"


def test_store_search_limit_offset(tmp_path: Path) -> None:
    store = SqliteStore(_db(tmp_path))
    for i in range(5):
        store.put(("t",), f"k{i}", {"i": i})
    results = store.search(("t",), limit=2, offset=2)
    assert len(results) == 2
    assert results[0].value["i"] == 2


def test_store_list_namespaces(tmp_path: Path) -> None:
    store = SqliteStore(_db(tmp_path))
    store.put(("t", "branch_a"), "k1", {})
    store.put(("t", "branch_b"), "k2", {})
    nss = store.list_namespaces(prefix=("t",))
    assert len(nss) >= 2
    assert ("t", "branch_a") in nss
    assert ("t", "branch_b") in nss


def test_store_list_namespaces_max_depth(tmp_path: Path) -> None:
    store = SqliteStore(_db(tmp_path))
    store.put(("t", "a", "x"), "k1", {})
    store.put(("t", "b"), "k2", {})
    nss = store.list_namespaces(prefix=("t",), max_depth=1)
    for ns in nss:
        assert len(ns) == 1


def test_workspace_auto_namespaces(tmp_path: Path) -> None:
    store = SqliteStore(_db(tmp_path))
    ws = ScopedWorkspace(store, ("thread-123",))
    ws.put("mykey", {"data": 42})
    ws.put("other", {"data": 99}, sub="branch_a")

    item = store.get(("thread-123",), "mykey")
    assert item is not None
    assert item.value == {"data": 42}

    item2 = store.get(("thread-123", "branch_a"), "other")
    assert item2 is not None
    assert item2.value == {"data": 99}


def test_workspace_search_scoped(tmp_path: Path) -> None:
    store = SqliteStore(_db(tmp_path))
    ws = ScopedWorkspace(store, ("t1",))
    ws.put("k1", {"val": 1})
    ws.put("k2", {"val": 2})

    ws2 = ScopedWorkspace(store, ("t2",))
    ws2.put("k3", {"val": 3})

    results = ws.search(limit=10)
    assert len(results) == 2
    assert results == [{"val": 1}, {"val": 2}]

    results2 = ws2.search(limit=10)
    assert len(results2) == 1
    assert results2 == [{"val": 3}]


def test_workspace_delete(tmp_path: Path) -> None:
    store = SqliteStore(_db(tmp_path))
    ws = ScopedWorkspace(store, ("t1",))
    ws.put("k", {"v": 1})
    ws.delete("k")
    assert ws.get("k") is None


def test_build_workspace_tools_put_get(tmp_path: Path) -> None:
    from nuself.agent.tools import build_workspace_tools
    store = SqliteStore(_db(tmp_path))
    ws = ScopedWorkspace(store, ("t1",))
    tools = build_workspace_tools(ws)
    tool_map = {t.name: t for t in tools}

    result = cast(Any, tool_map["workspace_put"]).invoke({"key": "k1", "value": '{"msg": "hello"}'})
    assert "Stored" in result

    result = cast(Any, tool_map["workspace_get"]).invoke({"key": "k1"})
    assert '"msg": "hello"' in result


def test_build_workspace_tools_search(tmp_path: Path) -> None:
    from nuself.agent.tools import build_workspace_tools
    store = SqliteStore(_db(tmp_path))
    ws = ScopedWorkspace(store, ("t1",))
    ws.put("a", {"type": "hypothesis", "text": "h1"})
    ws.put("b", {"type": "evidence", "text": "e1"})
    tools = build_workspace_tools(ws)
    tool_map = {t.name: t for t in tools}

    result = cast(Any, tool_map["workspace_search"]).invoke({"filter_json": '{"type": "hypothesis"}'})
    assert '"h1"' in result


def test_build_workspace_tools_delete(tmp_path: Path) -> None:
    from nuself.agent.tools import build_workspace_tools
    store = SqliteStore(_db(tmp_path))
    ws = ScopedWorkspace(store, ("t1",))
    ws.put("k", {"v": 1})
    tools = build_workspace_tools(ws)
    tool_map = {t.name: t for t in tools}

    result = cast(Any, tool_map["workspace_delete"]).invoke({"key": "k"})
    assert "Deleted" in result
    assert ws.get("k") is None


def test_build_workspace_tools_put_invalid_json(tmp_path: Path) -> None:
    from nuself.agent.tools import build_workspace_tools
    store = SqliteStore(_db(tmp_path))
    ws = ScopedWorkspace(store, ("t1",))
    tools = build_workspace_tools(ws)
    tool_map = {t.name: t for t in tools}

    result = cast(Any, tool_map["workspace_put"]).invoke({"key": "k", "value": "not json"})
    assert "Error" in result
