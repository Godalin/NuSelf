"""Agent middleware for execution safety and invocation-local caching."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from nuself.runtime.feature.effect import Execution
from nuself.runtime.feature.protocol import ToolEffectRequired
from nuself.runtime.messages import encode_json_value


@dataclass(frozen=True)
class ExecutedTool:
    """Minimal execution fact used for Agent retry safety."""

    name: str
    execution: Execution
    succeeded: bool

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("executed Tool name must not be blank")


class ToolCaptureMiddleware(AgentMiddleware):
    """Track execution and deduplicate calls within one Agent invocation.

    This middleware is not a logging or persistence authority. Tool
    observation belongs to the declaration interpreted by FeatureExecutor.
    """

    def __init__(
        self,
        *,
        captured: list[ExecutedTool] | None = None,
        cache: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self._captured = captured
        self._cache = cache
        self._cache_lock = threading.Lock()

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        tool_call = request.tool_call
        name: str = tool_call.get("name", "unknown")
        args: dict[str, Any] = tool_call.get("args", {})
        call_id: str | None = tool_call.get("id")
        execution = _tool_execution(request)
        cache_key = (
            _tool_cache_key(name, args)
            if self._cache is not None
            else None
        )
        if self._cache is not None and cache_key is not None:
            with self._cache_lock:
                cached = self._cache.get(cache_key)
            if cached is not None:
                return ToolMessage(
                    content=cached,
                    name=name,
                    tool_call_id=call_id or "",
                )

        try:
            result = handler(request)
        except ToolEffectRequired:
            raise
        except Exception:
            self._capture(ExecutedTool(name, execution, False))
            raise

        result_text = _middleware_result_text(result)
        if self._cache is not None and cache_key is not None:
            with self._cache_lock:
                self._cache[cache_key] = result_text
        self._capture(ExecutedTool(name, execution, True))
        return result

    def _capture(self, execution: ExecutedTool) -> None:
        if self._captured is not None:
            self._captured.append(execution)


def _tool_execution(request: ToolCallRequest) -> Execution:
    tool = request.tool
    if tool is None:
        return "mutating"
    metadata = tool.metadata or {}
    execution = metadata.get("execution")
    return execution if execution in {"readonly", "mutating"} else "mutating"


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
    """Extract human-readable text from a Tool result."""

    if isinstance(result, ToolMessage):
        content: Any = result.content  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
        if isinstance(content, str):
            return content
        return str(content)
    if isinstance(result, Command):  # pyright: ignore[reportUnnecessaryIsInstance]
        return f"<Command: goto={result.goto}>"
    return str(result)
