"""Generic isolated private workspaces for agent-facing services."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3

from nuself.config import runtime_paths

PRIVATE_WORKSPACE_SCHEMA_VERSION = "NuSelfPrivateWorkspace/v1"


@dataclass(frozen=True)
class PrivateWorkspacePaths:
    root: Path
    database: Path
    artifacts: Path
    notes: Path


class PrivateWorkspaceStore:
    """Manage isolated scratch workspaces under private/workspaces."""

    def __init__(self, project_root: Path | None = None, *, scope: str) -> None:
        _validate_segment(scope, "workspace scope")
        paths = runtime_paths(project_root)
        self._scope = scope
        self._root = paths.private_root / "workspaces" / scope

    @property
    def scope(self) -> str:
        return self._scope

    def paths(self, owner_id: str) -> PrivateWorkspacePaths:
        _validate_segment(owner_id, "workspace owner id")
        root = self._root / owner_id
        return PrivateWorkspacePaths(
            root=root,
            database=root / "workspace.sqlite",
            artifacts=root / "artifacts",
            notes=root / "notes",
        )

    def list_owners(self) -> list[str]:
        if not self._root.exists():
            return []
        return sorted(
            child.name for child in self._root.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        )

    def ensure(self, owner_id: str) -> PrivateWorkspacePaths:
        workspace = self.paths(owner_id)
        workspace.artifacts.mkdir(parents=True, exist_ok=True)
        workspace.notes.mkdir(parents=True, exist_ok=True)
        _initialize_workspace_database(workspace.database, scope=self._scope, owner_id=owner_id)
        return workspace


def _initialize_workspace_database(path: Path, *, scope: str, owner_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    created_at = datetime.now(UTC).isoformat()
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS workspace_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        metadata = {
            "schema": PRIVATE_WORKSPACE_SCHEMA_VERSION,
            "scope": scope,
            "owner_id": owner_id,
            "created_at": created_at,
        }
        conn.executemany(
            "INSERT OR IGNORE INTO workspace_meta (key, value) VALUES (?, ?)",
            metadata.items(),
        )
        conn.commit()
    finally:
        conn.close()


def _validate_segment(value: str, label: str) -> None:
    if value == "" or "/" in value or value in {".", ".."}:
        raise ValueError(f"invalid {label}: {value}")
