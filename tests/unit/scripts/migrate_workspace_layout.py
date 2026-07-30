from __future__ import annotations

# pyright: reportPrivateUsage=false

import json
from pathlib import Path
import runpy
import sqlite3
import subprocess
import sys
from typing import Callable, cast

from nuself.storage import _create_sqlite_backend

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "migrate_workspace_layout.py"
)
sys.path.insert(0, str(_SCRIPT.parents[1]))
migrate = cast(
    Callable[..., tuple[int, int]],
    runpy.run_path(str(_SCRIPT))["migrate"],
)


def test_imports_and_deletes_verified_legacy_workspace(tmp_path: Path) -> None:
    authority = tmp_path / ".nuself"
    authority.mkdir()
    _create_sqlite_backend(db_path=authority / "nuself.sqlite").close()
    owner_id = "reason-example"
    owner = authority / "workspaces" / "reason" / owner_id
    owner.mkdir(parents=True)
    legacy = sqlite3.connect(owner / "workspace.sqlite")
    try:
        legacy.execute(
            "CREATE TABLE workspace_meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        legacy.executemany(
            "INSERT INTO workspace_meta VALUES (?,?)",
            (("scope", "reason"), ("owner_id", owner_id)),
        )
        legacy.execute(
            "CREATE TABLE items (namespace TEXT, key TEXT, value TEXT, "
            "created_at TEXT, updated_at TEXT, PRIMARY KEY(namespace,key))"
        )
        legacy.execute(
            "INSERT INTO items VALUES (?,?,?,?,?)",
            (
                f"workspace/{owner_id}",
                "state",
                '{"answer":42}',
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        legacy.commit()
    finally:
        legacy.close()
    personas = owner / "persona_prompts"
    personas.mkdir()
    (personas / "pp_test.json").write_text(
        json.dumps({"id": "pp_test", "name": "tester"}),
        encoding="utf-8",
    )
    export = owner / "artifacts" / "export" / "jobs" / "job-1"
    export.mkdir(parents=True)
    (export / "combined.md").write_text("result", encoding="utf-8")

    assert migrate(
        authority,
        target="main",
        apply=False,
        delete_source=False,
    ) == (2, 1)
    assert migrate(
        authority,
        target="main",
        apply=True,
        delete_source=True,
    ) == (2, 1)

    assert not (authority / "workspaces").exists()
    assert not (authority / "backups").exists()
    assert (
        authority
        / "exports"
        / "reason"
        / owner_id
        / "jobs"
        / "job-1"
        / "combined.md"
    ).read_text(encoding="utf-8") == "result"
    connection = sqlite3.connect(authority / "nuself.sqlite")
    try:
        rows = connection.execute(
            "SELECT namespace,key,value FROM workspace_entries "
            "ORDER BY namespace,key"
        ).fetchall()
    finally:
        connection.close()
    assert rows[0][0:2] == (
        f"workspace/reason/{owner_id}",
        "state",
    )
    assert json.loads(rows[0][2]) == {"answer": 42}
    assert rows[1][0:2] == (
        f"workspace/reason/{owner_id}/persona_prompts",
        "pp_test",
    )

    assert migrate(
        authority,
        target="legacy",
        apply=False,
        delete_source=False,
    ) == (2, 1)
    assert migrate(
        authority,
        target="legacy",
        apply=True,
        delete_source=True,
    ) == (2, 1)
    restored = authority / "workspaces" / "reason" / owner_id
    assert (restored / "workspace.sqlite").is_file()
    assert (
        restored / "artifacts" / "export" / "jobs" / "job-1" / "combined.md"
    ).read_text(encoding="utf-8") == "result"
    connection = sqlite3.connect(authority / "nuself.sqlite")
    try:
        remaining = connection.execute(
            "SELECT COUNT(*) FROM workspace_entries "
            "WHERE namespace LIKE 'workspace/reason/%'"
        ).fetchone()
    finally:
        connection.close()
    assert remaining == (0,)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.migrate_database",
            str(authority / "nuself.sqlite"),
            "--to",
            "3",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    connection = sqlite3.connect(authority / "nuself.sqlite")
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        version = connection.execute(
            "SELECT MAX(version) FROM _schema_version"
        ).fetchone()
    finally:
        connection.close()
    assert version == (3,)
    assert "records" not in tables
    assert "workspace_entries" not in tables
