"""Explicit ReasonService composition helpers for tests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from nuself.application.trace import compose_trace_services
from nuself.config import runtime_paths
from nuself.reason.repository import ReasonRepository
from nuself.reason.scheduler import ReasonScheduler as _ReasonScheduler
from nuself.reason.service import (
    ReasonAdvancerProtocol,
    ReasonService as _ReasonService,
)
from tests.backend import owned_backend
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
        if repository is not None and project_root is None:
            raise ValueError(
                "tests must compose an injected reason repository with an "
                "explicit project_root"
            )
        root = runtime_paths(project_root).project_root
        backend = owned_backend(root)
        selected_repository = repository or ReasonRepository(
            runtime_paths(root),
            backend=backend,
        )
        selected_workspace = workspace_store or PrivateWorkspaceStore(
            runtime_paths(root),
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
        advancer: ReasonAdvancerProtocol | None = None,
        interval_seconds: int = 600,
        *,
        service: _ReasonService,
    ) -> None:
        super().__init__(
            project_root,
            advancer,
            interval_seconds,
            service=service,
        )
