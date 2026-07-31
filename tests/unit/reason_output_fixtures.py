"""Explicit ReasonOutputService composition helper for tests."""

from __future__ import annotations

from pathlib import Path

from nuself.config import runtime_paths
from nuself.reason.output import (
    ReasonOutputService as _ReasonOutputService,
    SectionPlanner,
)
from nuself.runtime.job_definitions import JobDefinitionRegistry
from nuself.runtime.jobs import JobSink
from nuself.reason.service import ReasonService
from nuself.workspace import PrivateWorkspaceStore


class ReasonOutputService(_ReasonOutputService):
    """Test wrapper that supplies the required reason workspace."""

    def __init__(
        self,
        project_root: Path,
        reason_service: ReasonService,
        *,
        job_sink: JobSink | None = None,
        job_definitions: JobDefinitionRegistry | None = None,
        section_planner: SectionPlanner | None = None,
    ) -> None:
        super().__init__(
            project_root,
            reason_service,
            workspace_store=PrivateWorkspaceStore(
                runtime_paths(project_root),
                scope="reason",
            ),
            job_sink=job_sink,
            job_definitions=job_definitions,
            section_planner=section_planner,
        )
