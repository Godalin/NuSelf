"""CLI adapter access to the application graph."""

from __future__ import annotations

from nuself.application.composition import ApplicationGraph
from nuself.application.runtime import (
    ApplicationRuntime,
    current_application_runtime,
)
from nuself.storage import ClosableStorageBackend


def _current_runtime() -> ApplicationRuntime:
    current = current_application_runtime()
    if current is None:
        raise RuntimeError("CLI application runtime is not active")
    return current


def cli_application() -> ApplicationGraph:
    """Borrow the graph owned by the active CLI runtime."""

    return _current_runtime().application


def cli_backend() -> ClosableStorageBackend:
    """Borrow storage for an explicit CLI infrastructure operation."""

    return _current_runtime().backend
