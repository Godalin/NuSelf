"""Shared LangGraph AgentMiddleware for tool call capture and logging."""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command


class ToolCaptureMiddleware(AgentMiddleware):
    """AgentMiddleware that captures, logs, and optionally caches tool calls.

    Replaces the per-file ``_LoggedTool`` (chat.py) and ``_CapturingTool``
    (advancer.py) pattern with a single LangGraph middleware hook.

    The same middleware instance can be reused across multiple agent
    invocations by calling ``reset()`` before each ``invoke()``.

    Parameters
    ----------
    log_callback:
        Called as ``log_callback(name, args, result=text)`` or
        ``log_callback(name, args, error=text)`` after each tool execution.
    captured:
        Mutable list to which ``(name, args, result)`` tuples are appended
        for post-execution inspection.
    cache:
        Mutable dict used for per-invocation deduplication keyed by
        ``"tool_name:{json(args)}"``.  When a cache hit is found the stored
        result is returned directly without calling the real tool.

    .. note::

       A single middleware can be configured for logging (chat), capture
       (reason advancer), or both simultaneously.
    """

    def __init__(
        self,
        *,
        log_callback: Callable[..., None] | None = None,
        captured: list[tuple[str, dict[str, object], str | None]] | None = None,
        cache: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self._log_callback = log_callback
        self._captured = captured
        self._cache = cache
        self._cache_lock = threading.Lock()

    def reset(
        self,
        *,
        log_callback: Callable[..., None] | None = None,
        captured: list[tuple[str, dict[str, object], str | None]] | None = None,
        cache: dict[str, str] | None = None,
    ) -> None:
        """Replace per-invocation state without rebuilding the middleware."""
        if log_callback is not None:
            self._log_callback = log_callback
        if captured is not None:
            self._captured = captured
        if cache is not None:
            self._cache = cache

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        tool_call = request.tool_call
        name: str = tool_call.get("name", "unknown")
        args: dict[str, Any] = tool_call.get("args", {})
        call_id: str | None = tool_call.get("id")

        if self._cache is not None:
            cache_key = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)}"
            with self._cache_lock:
                cached = self._cache.get(cache_key)
            if cached is not None:
                return ToolMessage(content=cached, name=name, tool_call_id=call_id or "")

        try:
            result = handler(request)
        except Exception as exc:
            if self._log_callback is not None:
                self._log_callback(name, args, error=str(exc))
            if self._captured is not None:
                self._captured.append((name, dict(args), str(exc)))
            raise

        result_text = _middleware_result_text(result)

        if self._cache is not None:
            cache_key = f"{name}:{json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)}"
            with self._cache_lock:
                self._cache[cache_key] = result_text

        if self._log_callback is not None:
            self._log_callback(name, args, result=result_text)
        if self._captured is not None:
            self._captured.append((name, dict(args), result_text))

        return result


def _middleware_result_text(result: ToolMessage | Command[Any]) -> str:
    """Extract human-readable text from a tool result."""
    if isinstance(result, ToolMessage):
        content: Any = result.content  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        if isinstance(content, str):
            return content
        return str(content)
    if isinstance(result, Command):  # pyright: ignore[reportUnnecessaryIsInstance]
        return f"<Command: goto={result.goto}>"
    return str(result)
