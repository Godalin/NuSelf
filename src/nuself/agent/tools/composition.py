"""Composition of domain-owned tools for the Chat runtime."""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.tools import BaseTool

from nuself.agent.tools.memory import build_memory_tool_set
from nuself.agent.tools.reason import build_reason_tools
from nuself.agent.tools.reflection import build_reflection_tools
from nuself.agent.tools.resources import ToolResources
from nuself.agent.tools.selves import build_selves_tools
from nuself.agent.tools.source import build_source_tools
from nuself.agent.tools.trace import build_trace_tools
from nuself.runtime.feature.execution import FeatureExecutor


def build_langchain_chat_tools(
    *,
    resources: ToolResources,
    selves_consult: Callable[[str, str, str | None], str] | None = None,
    feature_executor: FeatureExecutor | None = None,
) -> tuple[BaseTool, ...]:
    """Compose subsystem-owned tools for the chat runtime."""

    executor = feature_executor or FeatureExecutor()
    memory_tools = build_memory_tool_set(
        service=resources.memory,
        project_root=resources.project_root,
        executor=executor,
    )
    return (
        memory_tools.readonly
        + build_source_tools(resources.sources, project_root=resources.project_root, executor=executor)
        + build_reflection_tools(
            resources.reflections,
            executor=executor,
        )
        + memory_tools.write
        + build_reason_tools(
            service=resources.reasons,
            project_root=resources.project_root,
            job_sink=resources.job_sink,
            section_planner=resources.section_planner,
            executor=executor,
        )
        + build_trace_tools(
            resources.traces,
            executor=executor,
        )
        + build_selves_tools(selves_consult, executor=executor)
        + resources.persona_tools
    )
