"""Private memory root discovery and initialization."""

from __future__ import annotations

from pathlib import Path

from nuself.config import RuntimePaths, ensure_runtime_dirs, runtime_paths
from nuself.private_fs import ensure_private_directory


def get_private_root(project_root: Path | None = None) -> Path:
    """Return the ignored private memory root."""

    return runtime_paths(project_root).private_root


def ensure_private_root(project_root: Path | None = None) -> RuntimePaths:
    """Ensure the private root has the directories needed by the runtime."""

    paths = runtime_paths(project_root)
    ensure_private_directory(paths.private_root)
    ensure_private_directory(paths.private_root / "sources")
    ensure_private_directory(paths.private_root / "derived")
    ensure_private_directory(paths.private_root / "shares")
    ensure_runtime_dirs(paths)
    return paths
