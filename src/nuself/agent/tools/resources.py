"""Resolved capabilities borrowed by the agent-tool collection."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nuself.agent.text import TextAgent
from nuself.memory.service import MemoryService
from nuself.reason.output_contracts import SectionPlanner
from nuself.reason.service import ReasonService
from nuself.reflection.service import ReflectionService
from nuself.runtime.job.message import JobSink
from nuself.trace.service import TraceQueryService, TraceRecorder
from nuself.source.service import SourceService
from nuself.persona.service import PersonaService


@dataclass(frozen=True)
class ToolResources:
    """Tool-facing resources from one authority; owns no lifecycle."""

    project_root: Path
    memory: MemoryService
    sources: SourceService
    reflections: ReflectionService
    reasons: ReasonService
    traces: TraceQueryService
    personas: PersonaService
    persona_agent: TextAgent
    trace_recorder: TraceRecorder
    job_sink: JobSink | None = None
    section_planner: SectionPlanner | None = None
