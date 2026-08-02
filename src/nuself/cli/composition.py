"""CLI adapter access to the application graph."""

from __future__ import annotations

from pathlib import Path

from nuself.application.composition import ApplicationGraph
from nuself.application.runtime import (
    ApplicationRuntime,
    current_application_runtime,
)
from nuself.config import runtime_paths
from nuself.storage import ClosableStorageBackend


def _runtime_for_authority(
    project_root: Path | None,
) -> ApplicationRuntime:
    current = current_application_runtime()
    if current is None:
        raise RuntimeError("CLI application runtime is not active")
    requested = runtime_paths(project_root)
    if requested.authority_root != current.paths.authority_root:
        raise RuntimeError(
            "CLI handler requested a different authority than its "
            "application runtime"
        )
    return current


def compose_cli_application(
    project_root: Path | None,
) -> ApplicationGraph:
    """Compose one graph for a CLI command's selected authority."""

    return _runtime_for_authority(project_root).application


def compose_cli_backend(
    project_root: Path | None,
) -> ClosableStorageBackend:
    """Borrow storage for an explicit CLI infrastructure operation."""

    return _runtime_for_authority(project_root).backend
