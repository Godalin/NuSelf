"""Complete application service graph for one authority."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.application.memory import (
    MemoryRepositories,
    compose_memory_repositories,
)
from nuself.application.reason import compose_reason_repository
from nuself.application.reflection import compose_reflection_repository
from nuself.application.trace import TraceServices, compose_trace_services
from nuself.config import RuntimePaths
from nuself.reason.repository import ReasonRepository
from nuself.reflection.repository import ReflectionRepository
from nuself.storage import StorageBackend


@dataclass(frozen=True)
class ApplicationGraph:
    """Concrete services sharing one selected authority."""

    paths: RuntimePaths
    backend: StorageBackend
    memory: MemoryRepositories
    reason: ReasonRepository
    reflection: ReflectionRepository
    trace: TraceServices


def compose_application(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> ApplicationGraph:
    """Build the application graph from already-owned authority resources."""

    return ApplicationGraph(
        paths=paths,
        backend=backend,
        memory=compose_memory_repositories(paths, backend),
        reason=compose_reason_repository(paths, backend),
        reflection=compose_reflection_repository(paths, backend),
        trace=compose_trace_services(paths, backend),
    )
