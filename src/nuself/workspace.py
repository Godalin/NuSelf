"""Generic isolated private workspaces for agent-facing services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nuself.config import RuntimePaths


@dataclass(frozen=True)
class PrivateWorkspacePaths:
    root: Path
    database: Path


class PrivateWorkspaceStore:
    """Manage isolated scratch workspaces under one authority."""

    def __init__(self, paths: RuntimePaths, *, scope: str) -> None:
        _validate_segment(scope, "workspace scope")
        self._root = paths.exports_dir / scope
        self._db_path = paths.authority_root / "nuself.sqlite"

    def paths(self, owner_id: str) -> PrivateWorkspacePaths:
        _validate_segment(owner_id, "workspace owner id")
        root = self._root / owner_id
        return PrivateWorkspacePaths(
            root=root,
            database=self._db_path,
        )

    def list_owners(self) -> list[str]:
        if not self._root.exists():
            return []
        return sorted(
            child.name for child in self._root.iterdir()
            if child.is_dir() and not child.name.startswith(".")
        )

def _validate_segment(value: str, label: str) -> None:
    if value == "" or "/" in value or value in {".", ".."}:
        raise ValueError(f"invalid {label}: {value}")
