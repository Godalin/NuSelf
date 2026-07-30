"""Selected authority initialization helpers."""

from __future__ import annotations

from pathlib import Path

from nuself.config import RuntimePaths, ensure_runtime_dirs, runtime_paths
from nuself.private_fs import ensure_private_directory


def get_authority_root(authority_root: Path | None = None) -> Path:
    """Return the selected managed authority root."""

    return runtime_paths(authority_root).authority_root


def ensure_authority_root(
    authority_root: Path | None = None,
) -> RuntimePaths:
    """Ensure directories required by the selected authority runtime."""

    paths = runtime_paths(authority_root)
    ensure_private_directory(paths.authority_root)
    ensure_private_directory(paths.authority_root / "sources")
    ensure_private_directory(paths.authority_root / "derived")
    ensure_private_directory(paths.authority_root / "shares")
    ensure_runtime_dirs(paths)
    return paths
