"""CLI adapter access to the application graph."""

from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path

from nuself.conversation import ConversationStore
from nuself.application.composition import ApplicationGraph
from nuself.application.runtime import (
    ApplicationRuntime,
    current_application_runtime,
    use_application_runtime,
)
from nuself.config import runtime_paths

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
    if current is None:
        raise RuntimeError("CLI application runtime is not active")
    requested = runtime_paths(project_root)
    if requested.project_root != current.paths.project_root:
        raise RuntimeError(
            "CLI handler requested a different authority than its "
            "application runtime"
        )
    return current.application


def compose_cli_conversation_store(
    project_root: Path | None,
) -> ConversationStore:
    """Borrow conversation persistence from the invocation application."""

    return compose_cli_application(project_root).conversations
