"""Shared LangGraph AgentMiddleware for tool call capture and logging."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Mapping, cast

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from nuself.runtime import encode_json_value, freeze_json_value
from nuself.runtime.diagnostics import emit_runtime_warning


@dataclass(frozen=True)
class ToolOutcome:
    """One immutable internal tool execution outcome."""

    name: str
    args: Mapping[str, object]
    result: str | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if (self.result is None) == (self.error is None):
            raise ValueError(
                "tool outcome requires exactly one of result or error"
            )
        frozen = freeze_json_value(dict(self.args))
        if not isinstance(frozen, Mapping):
            raise TypeError("tool outcome args must be a mapping")
        object.__setattr__(
            self,
            "args",
            cast(Mapping[str, object], frozen),
        )

    @classmethod
    def succeeded(
        cls,
        name: str,
        args: Mapping[str, object],
        result: str,
    ) -> ToolOutcome:
        return cls(name=name, args=args, result=result)

    @classmethod
    def failed(
        cls,
        name: str,
        args: Mapping[str, object],
        error: str,
    ) -> ToolOutcome:
        return cls(name=name, args=args, error=error)


class ToolCaptureMiddleware(AgentMiddleware):
    """AgentMiddleware that captures, logs, and optionally caches tool calls.

    Replaces the per-file ``_LoggedTool`` (chat.py) and ``_CapturingTool``
    (advancer.py) pattern with a single LangGraph middleware hook.

    Parameters
    ----------
    log_callback:
        Called as ``log_callback(name, args, result=text)`` or
        ``log_callback(name, args, error=text)`` after each tool execution.
    log_error_callback:
        Called when ``log_callback`` fails. Neither callback may change the
        primary tool result or exception.
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
        log_error_callback: Callable[[Exception], None] | None = None,
        captured: list[ToolOutcome] | None = None,
        cache: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self._log_callback = log_callback
        self._log_error_callback = log_error_callback
        self._captured = captured
        self._cache = cache
        self._cache_lock = threading.Lock()

    def _log(
        self,
        name: str,
        args: dict[str, Any],
        **outcome: str,
    ) -> None:
        """Project one tool outcome without changing the primary operation."""

        if self._log_callback is None:
            return
        try:
            self._log_callback(name, args, **outcome)
        except Exception as exc:  # noqa: BLE001 - observer failures are secondary
            if self._log_error_callback is not None:
                try:
                    self._log_error_callback(exc)
                    return
                except Exception as report_exc:  # noqa: BLE001 - preserve primary outcome
                    emit_runtime_warning(
                        "tool log callback failed: "
                        f"{exc}; failure reporter failed: {report_exc}",
                        stacklevel=3,
                    )
                    return
            emit_runtime_warning(
                f"tool log callback failed: {exc}",
                stacklevel=3,
            )

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        tool_call = request.tool_call
        name: str = tool_call.get("name", "unknown")
        args: dict[str, Any] = tool_call.get("args", {})
        call_id: str | None = tool_call.get("id")

        cache_key = (
            _tool_cache_key(name, args)
            if self._cache is not None
            else None
        )
        if self._cache is not None and cache_key is not None:
            with self._cache_lock:
                cached = self._cache.get(cache_key)
            if cached is not None:
                return ToolMessage(content=cached, name=name, tool_call_id=call_id or "")

        try:
            result = handler(request)
        except Exception as exc:
            self._log(name, args, error=str(exc))
            if self._captured is not None:
                self._captured.append(
                    ToolOutcome.failed(name, args, str(exc))
                )
            raise

        result_text = _middleware_result_text(result)

        if self._cache is not None and cache_key is not None:
            with self._cache_lock:
                self._cache[cache_key] = result_text

        self._log(name, args, result=result_text)
        if self._captured is not None:
            self._captured.append(
                ToolOutcome.succeeded(name, args, result_text)
            )

        return result


def _tool_cache_key(
    tool_name: str,
    args: dict[str, Any],
) -> str | None:
    try:
        canonical = encode_json_value(
            args,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except TypeError:
        return None
    return f"{tool_name}:{canonical}"


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
