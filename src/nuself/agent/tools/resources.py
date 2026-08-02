"""Resolved capabilities borrowed by the agent-tool collection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from langchain_core.tools import BaseTool

from nuself.memory.service import MemoryService
from nuself.reason.output_contracts import SectionPlanner
from nuself.reason.service import ReasonService
from nuself.reflection.service import ReflectionService
from nuself.runtime.jobs import JobSink
from nuself.trace.service import TraceQueryService
from nuself.workspace import PrivateWorkspaceStore


@dataclass(frozen=True)
class ToolResources:
    """Tool-facing resources from one authority; owns no lifecycle."""

    project_root: Path
    memory: MemoryService
    reflections: ReflectionService
    reasons: ReasonService
    reason_workspace: PrivateWorkspaceStore
    traces: TraceQueryService
    persona_tools: tuple[BaseTool, ...]
    job_sink: JobSink | None = None
    section_planner: SectionPlanner | None = None
