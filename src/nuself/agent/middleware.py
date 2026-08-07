"""Agent middleware for execution safety and invocation-local caching."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command

from nuself.agent.outcome import ToolOutcome, ToolOutcomeProjection
from nuself.agent.tool_utils import tool_service_component
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.feature.effect import Execution
from nuself.runtime.feature.protocol import ToolEffectRequired
from nuself.runtime.messages import encode_json_value
from nuself.runtime.warning import (
    TerminalWarningDefinition,
    TerminalWarningRegistry,
    TerminalWarningSchemaError,
    emit_registered_terminal_warning,
)

TOOL_OUTCOME_CAPTURE_FAILED = "agent/tool_outcome_capture_failed"
TOOL_OUTCOME_REPORTER_FAILED = "agent/tool_outcome_reporter_failed"


def _validate_outcome_warning(metadata: Mapping[str, object]) -> None:
    for field, value in metadata.items():
        if not isinstance(value, str) or not value.strip():
            raise TerminalWarningSchemaError(
                f"agent Tool outcome warning {field} must be non-blank"
            )


AGENT_TOOL_OUTCOME_WARNINGS = (
    TerminalWarningRegistry()
    .register(
        TerminalWarningDefinition(
            TOOL_OUTCOME_CAPTURE_FAILED,
            ("tool", "error"),
            _validate_outcome_warning,
        )
    )
    .register(
        TerminalWarningDefinition(
            TOOL_OUTCOME_REPORTER_FAILED,
            ("tool", "error", "reporter_error"),
            _validate_outcome_warning,
        )
    )
    .seal()
)


class ToolCaptureMiddleware(AgentMiddleware):
    """Track execution and deduplicate calls within one Agent invocation.

    This middleware is not a logging or persistence authority. Tool
    observation belongs to the declaration interpreted by FeatureExecutor.
    """

    def __init__(
        self,
        *,
        captured: list[ToolOutcome] | None = None,
        cache: dict[str, str] | None = None,
        outcomes: ToolOutcomeProjection | None = None,
    ) -> None:
        super().__init__()
        self._captured = captured
        self._cache = cache
        self._outcomes = outcomes
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
        service_component = tool_service_component(request.tool)
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
        except Exception as error:
            self._capture_and_project(
                name,
                execution,
                args,
                service_component=service_component,
                error=diagnostic_exception_message(error),
            )
            raise

        result_text = _middleware_result_text(result)
        if self._cache is not None and cache_key is not None:
            with self._cache_lock:
                self._cache[cache_key] = result_text
        self._capture_and_project(
            name,
            execution,
            args,
            service_component=service_component,
            result=result_text,
        )
        return result

    def _capture_and_project(
        self,
        name: str,
        execution: Execution,
        args: dict[str, Any],
        *,
        service_component: str | None,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        if self._captured is None and self._outcomes is None:
            return
        try:
            outcome = ToolOutcome(
                name=name,
                execution=execution,
                args=args,
                result=result,
                error=error,
            )
        except Exception as capture_error:
            self._report_capture_failure(capture_error, tool=name)
            return
        if self._captured is not None:
            self._captured.append(outcome)
        if self._outcomes is not None:
            if service_component is None:
                self._report_capture_failure(
                    ValueError("Tool has no service component metadata"),
                    tool=name,
                )
                return
            try:
                self._outcomes.project_best_effort(
                    outcome,
                    service_component=service_component,
                )
            except Exception as projection_error:
                self._report_capture_failure(projection_error, tool=name)

    def _report_capture_failure(
        self,
        error: Exception,
        *,
        tool: str,
    ) -> None:
        if self._outcomes is not None:
            try:
                self._outcomes.report_capture_failure(error, tool=tool)
                return
            except Exception as reporter_error:
                emit_registered_terminal_warning(
                    AGENT_TOOL_OUTCOME_WARNINGS,
                    TOOL_OUTCOME_REPORTER_FAILED,
                    {
                        "tool": tool,
                        "error": diagnostic_exception_message(error),
                        "reporter_error": diagnostic_exception_message(
                            reporter_error
                        ),
                    },
                    stacklevel=3,
                )
                return
        emit_registered_terminal_warning(
            AGENT_TOOL_OUTCOME_WARNINGS,
            TOOL_OUTCOME_CAPTURE_FAILED,
            {
                "tool": tool,
                "error": diagnostic_exception_message(error),
            },
            stacklevel=3,
        )


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
