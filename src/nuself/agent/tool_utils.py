"""Shared tool formatting utilities for agent subsystems."""

from __future__ import annotations

import json
from typing import Any, cast


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
        lines.append(f"result: {_format_tool_debug_result(result, limit=limit)}")
    if error is not None:
        lines.append(f"error: {_truncate_tool_debug_text(error, limit=limit)}")
    return "\n".join(lines)


def _format_tool_debug_value(value: object, limit: int = 200) -> str:
    if isinstance(value, dict):
        d: dict[str, object] = cast("dict[str, object]", value)
        if len(d) == 1 and "_raw" in d:
            raw = d["_raw"]
            return _truncate_tool_debug_text(raw if isinstance(raw, str) else str(raw), limit=limit)
        return _truncate_tool_debug_text(
            json.dumps(d, indent=2, sort_keys=True, ensure_ascii=False, default=str), limit=limit
        )
    try:
        return _truncate_tool_debug_text(
            json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str), limit=limit
        )
    except (TypeError, ValueError):
        return _truncate_tool_debug_text(str(value), limit=limit)


def _format_tool_debug_result(text: str, limit: int = 200) -> str:
    """Format result text — try JSON pretty-print, fall back to raw."""
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return _truncate_tool_debug_text(text, limit=limit)
    return _truncate_tool_debug_text(
        json.dumps(parsed, indent=2, sort_keys=True, ensure_ascii=False, default=str), limit=limit
    )


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
