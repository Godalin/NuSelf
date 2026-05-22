"""Shared tool formatting utilities for agent subsystems."""

from __future__ import annotations

import json
from typing import Any


def format_tool_debug_body(
    *,
    args: dict[str, Any],
    result: str | None = None,
    error: str | None = None,
    full: bool = False,
) -> str:
    """Format tool call args, result, and error into log body text."""
    limit = 0 if full else 200
    lines = [f"args: {_format_tool_debug_value(args, limit=limit)}"]
    if result is not None:
        lines.append(f"result: {_truncate_tool_debug_text(result, limit=limit)}")
    if error is not None:
        lines.append(f"error: {_truncate_tool_debug_text(error, limit=limit)}")
    return "\n".join(lines)


def _format_tool_debug_value(value: object, limit: int = 200) -> str:
    try:
        return _truncate_tool_debug_text(
            json.dumps(value, sort_keys=True, ensure_ascii=False, default=str), limit=limit
        )
    except (TypeError, ValueError):
        return _truncate_tool_debug_text(str(value), limit=limit)


def _truncate_tool_debug_text(text: str, limit: int = 200) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def tool_result_text(result: object) -> str:
    """Extract human-readable text from a tool result."""
    content = getattr(result, "content", None)
    if isinstance(content, str):
        return content
    return str(result)
