"""CLI adapter access to the application graph."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path

from nuself.application.composition import (
    ApplicationGraph,
    compose_application,
)
from nuself.application.runtime import (
    ApplicationRuntime,
    current_application_runtime,
    use_application_runtime,
)
from nuself.config import runtime_paths
from nuself.storage import get_default_backend

def use_cli_application_runtime(
    runtime: ApplicationRuntime,
) -> AbstractContextManager[None]:
    """Expose one borrowed graph to every handler in a CLI invocation."""

    return use_application_runtime(runtime)


def compose_cli_application(
    project_root: Path | None,
) -> ApplicationGraph:
    """Compose one graph for a CLI command's selected authority."""

    current = current_application_runtime()
    if current is not None:
        requested = runtime_paths(project_root)
        if requested.project_root != current.paths.project_root:
            raise RuntimeError(
                "CLI handler requested a different authority than its "
                "application runtime"
            )
        return current.application
    return compose_application(
        runtime_paths(project_root),
        get_default_backend(project_root),
    )
