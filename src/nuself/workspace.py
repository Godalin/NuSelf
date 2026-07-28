"""Generic isolated private workspaces for agent-facing services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nuself.config import runtime_paths
from nuself.private_fs import ensure_private_directory

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
        self._project_root = project_root
        self._scope = scope
        self._root = paths.private_root / "workspaces" / scope
        self._db_path = paths.private_root / "nuself.sqlite"

    @property
    def scope(self) -> str:
        return self._scope

    @property
    def database(self) -> Path:
        return self._db_path

    def paths(self, owner_id: str) -> PrivateWorkspacePaths:
        _validate_segment(owner_id, "workspace owner id")
        root = self._root / owner_id
        return PrivateWorkspacePaths(
            root=root,
            database=self._db_path,
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
        ensure_private_directory(workspace.artifacts)
        ensure_private_directory(workspace.notes)
        return workspace


def _validate_segment(value: str, label: str) -> None:
    if value == "" or "/" in value or value in {".", ".."}:
        raise ValueError(f"invalid {label}: {value}")
