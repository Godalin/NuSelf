"""CLI adapter access to the application graph."""

from __future__ import annotations

from pathlib import Path

from nuself.application.composition import (
    ApplicationGraph,
    compose_application,
)
from nuself.config import runtime_paths
from nuself.storage import get_default_backend


def compose_cli_application(
    project_root: Path | None,
) -> ApplicationGraph:
    """Compose one graph for a CLI command's selected authority."""

    return compose_application(
        runtime_paths(project_root),
        get_default_backend(project_root),
    )
