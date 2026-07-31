"""Application-owned composition for the trace domain."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.config import RuntimePaths
from nuself.storage import StorageBackend
from nuself.trace.repository import TraceRepository
from nuself.trace.service import TraceQueryService, TraceRecorder


@dataclass(frozen=True)
class TraceServices:
    """Concrete trace capabilities for one authority."""

    repository: TraceRepository
    recorder: TraceRecorder
    query: TraceQueryService


def compose_trace_services(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> TraceServices:
    """Compose trace capabilities from already-owned resources."""

    repository = TraceRepository(paths, backend=backend)
    return TraceServices(
        repository=repository,
        recorder=TraceRecorder(repository),
        query=TraceQueryService(repository),
    )
