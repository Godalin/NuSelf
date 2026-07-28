"""Shared tool utilities for agent subsystems."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

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


def tool_log_metadata(
    *,
    args: Mapping[str, Any],
    result: str | None = None,
    error: str | None = None,
    service_component: str,
    tool_name: str,
) -> dict[str, object]:
    """Build structured metadata for a service tool call log."""
    metadata: dict[str, object] = {
        "service_component": service_component,
        "tool": tool_name,
        "args": dict(args),
    }
    if result is not None:
        metadata["result"] = result
    if error is not None:
        metadata["error"] = error
    return metadata


def tool_result_text(result: object) -> str:
    """Extract human-readable text from a tool result."""
    content = getattr(result, "content", None)
    if isinstance(content, str):
        return content
    return str(result)
