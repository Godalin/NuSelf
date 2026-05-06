"""Private memory root discovery and initialization."""

from __future__ import annotations

from pathlib import Path

from nuself.config import RuntimePaths, ensure_runtime_dirs, runtime_paths


def get_private_root(project_root: Path | None = None) -> Path:
    """Return the ignored private memory root."""

    return runtime_paths(project_root).private_root


def ensure_private_root(project_root: Path | None = None) -> RuntimePaths:
    """Ensure the private root has the directories needed by the runtime."""

    paths = runtime_paths(project_root)
    paths.private_root.mkdir(parents=True, exist_ok=True)
    (paths.private_root / "sources").mkdir(exist_ok=True)
    (paths.private_root / "derived").mkdir(exist_ok=True)
    (paths.private_root / "shares").mkdir(exist_ok=True)
    ensure_runtime_dirs(paths)
    return paths

