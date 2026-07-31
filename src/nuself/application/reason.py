"""Application-owned composition for the reason domain."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from nuself.config import RuntimePaths
import nuself.reason.service as reason_service_module
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonAdvancerProtocol, ReasonService
from nuself.storage import StorageBackend
from nuself.workspace import PrivateWorkspaceStore

if TYPE_CHECKING:
    from nuself.application.composition import ApplicationGraph


def compose_reason_repository(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> ReasonRepository:
    """Compose reason persistence from already-owned resources."""

    return ReasonRepository(paths, backend=backend)


def compose_reason_service(
    application: "ApplicationGraph",
    *,
    advancer: ReasonAdvancerProtocol | None = None,
    prompt_generator: Callable[..., str] | None = None,
) -> ReasonService:
    """Compose reason operations from one authority-owned graph."""

    return ReasonService(
        application.paths.project_root,
        repository=application.reason,
        workspace_store=PrivateWorkspaceStore(
            application.paths.project_root,
            scope="reason",
        ),
        trace_recorder=application.trace.recorder,
        advancer=advancer,
        prompt_generator=(
            prompt_generator
            or reason_service_module.generate_reasoning_prompt
        ),
    )
