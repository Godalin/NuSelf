"""Shared tool utilities for agent subsystems."""

from __future__ import annotations

from collections.abc import Iterable

from langchain_core.tools import BaseTool


def tool_service_component(tool: BaseTool) -> str | None:
    """Return a framework tool's validated service component."""
    metadata = tool.metadata or {}
    service_component = metadata.get("service_component")
    return service_component if isinstance(service_component, str) else None


def index_tool_service_components(
    tools: Iterable[BaseTool],
) -> dict[str, str]:
    """Index tool names by their validated service components."""
    components: dict[str, str] = {}
    for tool in tools:
        service_component = tool_service_component(tool)
        if service_component is not None:
            components[tool.name] = service_component
    return components
