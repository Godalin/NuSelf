"""Trace package composition for one selected authority."""

from __future__ import annotations

from pathlib import Path

from nuself.storage import StorageBackend
from nuself.trace.repository import TraceRepository
from nuself.trace.service import TraceQueryService, TraceRecorder


def build_trace_repository(
    project_root: Path | None,
    *,
    backend: StorageBackend,
) -> TraceRepository:
    """Build a trace repository from explicitly owned storage."""

    return TraceRepository(project_root, backend=backend)


def build_trace_recorder(
    project_root: Path | None,
    *,
    backend: StorageBackend,
) -> TraceRecorder:
    """Build the trace write service at the package boundary."""

    return TraceRecorder(
        build_trace_repository(project_root, backend=backend)
    )


def build_trace_query_service(
    project_root: Path | None,
    *,
    backend: StorageBackend,
) -> TraceQueryService:
    """Build the trace read service at the package boundary."""

    return TraceQueryService(
        build_trace_repository(project_root, backend=backend)
    )
