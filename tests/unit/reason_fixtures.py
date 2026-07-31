"""Explicit ReasonService composition helpers for tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from nuself.application import compose_trace_services
from nuself.config import runtime_paths
from nuself.reason.repository import ReasonRepository
from nuself.reason.advancer import ReasonAdvancer
from nuself.reason.scheduler import ReasonScheduler as _ReasonScheduler
from nuself.reason.service import (
    ReasonAdvancerProtocol,
    ReasonService as _ReasonService,
)
from nuself.storage import get_default_backend
from nuself.trace.service import TraceRecorder
from nuself.workspace import PrivateWorkspaceStore


class ReasonService(_ReasonService):
    """Test convenience wrapper that still supplies every required resource."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        repository: ReasonRepository | None = None,
        workspace_store: PrivateWorkspaceStore | None = None,
        trace_recorder: TraceRecorder | None = None,
        advancer: ReasonAdvancerProtocol | None = None,
        prompt_generator: Callable[..., str] | None = None,
    ) -> None:
        root = (
            repository.project_root
            if repository is not None
            and repository.project_root is not None
            else runtime_paths(project_root).project_root
        )
        backend = get_default_backend(root)
        selected_repository = repository or ReasonRepository(
            runtime_paths(root),
            backend=backend,
        )
        selected_workspace = workspace_store or PrivateWorkspaceStore(
            root,
            scope="reason",
        )
        selected_trace = trace_recorder or compose_trace_services(
            runtime_paths(root),
            backend,
        ).recorder
        super().__init__(
            root,
            repository=selected_repository,
            workspace_store=selected_workspace,
            trace_recorder=selected_trace,
            advancer=advancer,
            prompt_generator=prompt_generator,
        )


class ReasonScheduler(_ReasonScheduler):
    """Test wrapper that supplies the service-owned repository explicitly."""

    def __init__(
        self,
        project_root: Path | None = None,
        advancer: ReasonAdvancer | None = None,
        interval_seconds: int = 600,
        *,
        service: _ReasonService,
        repository: ReasonRepository | None = None,
    ) -> None:
        super().__init__(
            project_root,
            advancer,
            interval_seconds,
            service=service,
            repository=repository or service.repository,
        )
