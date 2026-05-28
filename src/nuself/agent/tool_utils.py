"""Shared tool utilities for agent subsystems."""

from __future__ import annotations

from typing import Any


def tool_log_metadata(
    *,
    args: dict[str, Any],
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
