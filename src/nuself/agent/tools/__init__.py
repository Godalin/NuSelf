"""Public composition boundary for framework-native agent tools."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from langchain_core.tools import BaseTool

from nuself.application import compose_trace_services
from nuself.agent.tools.memory import build_memory_tool_set
from nuself.agent.tools.reason import build_reason_tools
from nuself.agent.tools.reflection import build_reflection_tools
from nuself.agent.tools.selves import build_selves_tools
from nuself.agent.tools.trace import build_trace_tools
from nuself.agent.tools.workspace import (
    build_workspace_tools,
    build_workspace_tools_from_provider,
)
from nuself.config import runtime_paths
from nuself.memory.query import MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.persona.tools import build_persona_tools
from nuself.reason.output import SectionPlanner
from nuself.reason.service import ReasonService
from nuself.reflection.repository import ReflectionRepository
from nuself.runtime.jobs import JobSink
from nuself.storage import get_default_backend

__all__ = [
    "build_langchain_chat_tools",
    "build_workspace_tools",
    "build_workspace_tools_from_provider",
]


def build_langchain_chat_tools(
    *,
    query_service: MemoryQueryService,
    memory_repository: MemoryEntryRepository,
    reflection_repository: ReflectionRepository,
    project_root: Path | None,
    selves_consult: Callable[[str, str, str | None], str] | None = None,
    job_sink: JobSink | None = None,
    section_planner: SectionPlanner | None = None,
) -> tuple[BaseTool, ...]:
    """Compose subsystem-owned tools for the chat runtime."""
    memory_tools = build_memory_tool_set(
        query_service=query_service,
        repository=memory_repository,
        project_root=project_root,
    )
    return (
        memory_tools.readonly
        + build_reflection_tools(reflection_repository)
        + memory_tools.write
        + build_reason_tools(
            service=ReasonService(project_root),
            project_root=project_root,
            job_sink=job_sink,
            section_planner=section_planner,
        )
        + build_trace_tools(
            compose_trace_services(
                runtime_paths(project_root),
                get_default_backend(project_root),
            ).query
        )
        + build_selves_tools(selves_consult)
        + build_persona_tools(project_root)
    )
