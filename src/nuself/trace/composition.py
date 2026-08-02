"""Trace-owned capability composition from supplied resources."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.config import RuntimePaths
from nuself.storage import StorageBackend
from nuself.trace.repository import TraceRepository
from nuself.trace.service import TraceQueryService, TraceRecorder


@dataclass(frozen=True)
class TraceServices:
    """Concrete trace capabilities for one authority."""

    recorder: TraceRecorder
    query: TraceQueryService


def compose_trace_services(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> TraceServices:
    """Compose trace capabilities from already-owned resources."""

    repository = TraceRepository(paths, backend=backend)
    return TraceServices(
        recorder=TraceRecorder(repository),
        query=TraceQueryService(repository),
    )
