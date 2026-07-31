"""Public composition boundary for framework-native agent tools."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from langchain_core.tools import BaseTool

from nuself.agent.tools.memory import build_memory_tool_set
from nuself.agent.tools.reason import build_reason_tools
from nuself.agent.tools.reflection import build_reflection_tools
from nuself.agent.tools.selves import build_selves_tools
from nuself.agent.tools.trace import build_trace_tools
from nuself.agent.tools.workspace import (
    build_workspace_tools,
    build_workspace_tools_from_provider,
)
from nuself.memory.query import MemoryQueryService
from nuself.memory.repository import MemoryEntryRepository
from nuself.reason.output_contracts import SectionPlanner
from nuself.reason.service import ReasonService
from nuself.reflection.repository import ReflectionRepository
from nuself.runtime.jobs import JobSink
from nuself.trace.service import TraceQueryService
from nuself.workspace import PrivateWorkspaceStore

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
    reason_service: ReasonService,
    trace_query_service: TraceQueryService,
    persona_tools: Sequence[BaseTool],
    project_root: Path,
    reason_workspace_store: PrivateWorkspaceStore,
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
            service=reason_service,
            project_root=project_root,
            workspace_store=reason_workspace_store,
            job_sink=job_sink,
            section_planner=section_planner,
        )
        + build_trace_tools(
            trace_query_service
        )
        + build_selves_tools(selves_consult)
        + tuple(persona_tools)
    )
