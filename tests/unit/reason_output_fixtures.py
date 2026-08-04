"""Explicit ReasonOutputService composition helper for tests."""

from __future__ import annotations

from pathlib import Path

from nuself.reason.output import ReasonOutputService as _ReasonOutputService
from nuself.reason.output_contracts import SectionPlanner
from nuself.reason.service import ReasonService


class ReasonOutputService(_ReasonOutputService):
    """Test wrapper that supplies the required reason workspace."""

    def __init__(
        self,
        project_root: Path,
        reason_service: ReasonService,
        *,
        section_planner: SectionPlanner | None = None,
    ) -> None:
        super().__init__(
            project_root,
            reason_service,
            section_planner=section_planner,
        )
