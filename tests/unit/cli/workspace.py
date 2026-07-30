"""Tests for generic private workspaces."""

from __future__ import annotations

# pyright: reportPrivateUsage=false

from pathlib import Path
import sqlite3

import pytest

from nuself.workspace import PrivateWorkspaceStore
from nuself.storage import _create_sqlite_backend


def test_private_workspace_store_resolves_main_authority_without_side_tree(
    tmp_path: Path,
) -> None:
    _create_sqlite_backend(db_path=tmp_path / "nuself.sqlite").close()
    store = PrivateWorkspaceStore(tmp_path, scope="reason")

    workspace = store.ensure("reason-abc")

    db_path = tmp_path / "nuself.sqlite"
    assert workspace.root == tmp_path / "exports" / "reason" / "reason-abc"
    assert workspace.database == db_path
    assert not workspace.root.exists()

    from nuself.store import SqliteStore
    s = SqliteStore(db_path)
    s.put(("reason-abc",), "key", {"hello": "world"})
    assert db_path.is_file()
    assert not (tmp_path / "workspaces").exists()
    conn = sqlite3.connect(str(db_path))
    try:
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "workspace_entries" in tables
    finally:
        conn.close()


def test_private_workspace_store_rejects_path_segments(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        PrivateWorkspaceStore(tmp_path, scope="../bad")

    store = PrivateWorkspaceStore(tmp_path, scope="reason")
    with pytest.raises(ValueError):
        store.ensure("../bad")
