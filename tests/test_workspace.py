"""Tests for generic private workspaces."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from nuself.workspace import PRIVATE_WORKSPACE_SCHEMA_VERSION, PrivateWorkspaceStore


def test_private_workspace_store_initializes_sqlite(tmp_path: Path) -> None:
    store = PrivateWorkspaceStore(tmp_path, scope="reason")

    workspace = store.ensure("reason-abc")

    assert workspace.root == tmp_path / "private" / "workspaces" / "reason" / "reason-abc"
    assert workspace.database.is_file()
    assert workspace.artifacts.is_dir()
    assert workspace.notes.is_dir()
    conn = sqlite3.connect(workspace.database)
    rows = dict(conn.execute("SELECT key, value FROM workspace_meta").fetchall())
    conn.close()
    assert rows["schema"] == PRIVATE_WORKSPACE_SCHEMA_VERSION
    assert rows["scope"] == "reason"
    assert rows["owner_id"] == "reason-abc"
    assert rows["created_at"]


def test_private_workspace_store_rejects_path_segments(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        PrivateWorkspaceStore(tmp_path, scope="../bad")

    store = PrivateWorkspaceStore(tmp_path, scope="reason")
    with pytest.raises(ValueError):
        store.ensure("../bad")
