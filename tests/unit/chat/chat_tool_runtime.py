from __future__ import annotations

# pyright: reportPrivateUsage=false

from pathlib import Path
from langchain_core.tools import BaseTool

from nuself.agent.chat.tool_runtime import ConversationToolRuntime
from nuself.agent.middleware import ToolOutcome
from nuself.agent.tools.decorated import materialize_tool
from nuself.decorators import compact, component, observed, readonly, tool
from nuself.log.reader import read_log_events
from nuself.runtime.event.payload import RuntimeLogEventPayload
from nuself.runtime.event.publisher import EventPublisher
from nuself.runtime.feature.execution import FeatureExecutor
from nuself.runtime.messages import RuntimeEnvelope


def test_tool_log_failure_reporter_writes_structured_degradation(
    tmp_path: Path,
) -> None:
    runtime = object.__new__(ConversationToolRuntime)
    runtime._project_root = tmp_path

    runtime.report_log_failure(OSError("audit unavailable"))

    [event] = read_log_events(project_root=tmp_path, component="chat")
    assert event.event == "observability_projection_failed"
    assert event.status == "degraded"
    assert event.error == "audit unavailable"
    assert event.metadata == {"failed_event": "service_tool_called"}


def _runtime_with_observed_tool(*, compact_output: bool = False) -> tuple[ConversationToolRuntime, list[RuntimeEnvelope]]:
    @tool(name="memory_search", description="Search memory.")
    @component("memory")
    @readonly
    @observed
    def search(query: str) -> str:
        return query

    if compact_output:
        compact(search)
    framework_tool = materialize_tool(search, executor=FeatureExecutor())
    publisher = EventPublisher()
    captured: list[RuntimeEnvelope] = []
    publisher.attach_projection(captured.append)
    runtime = object.__new__(ConversationToolRuntime)
    tools: dict[str, BaseTool] = {framework_tool.name: framework_tool}
    runtime._tools = tools
    runtime._event_publisher = publisher
    runtime._project_root = Path(".")
    return runtime, captured


def test_observed_tool_activity_includes_structured_io_by_default() -> None:
    runtime, captured = _runtime_with_observed_tool()

    runtime.log_outcome(
        ToolOutcome(
            name="memory_search",
            args={"query": "architecture"},
            result="one match",
        )
    )

    [event] = captured
    payload = RuntimeLogEventPayload.from_mapping(event.payload)
    assert payload.metadata == {
        "service_component": "memory",
        "operation": "memory_search",
        "tool": "memory_search",
        "args": {"query": "architecture"},
        "result": "one match",
    }


def test_compact_tool_activity_omits_arguments_and_result() -> None:
    runtime, captured = _runtime_with_observed_tool(compact_output=True)

    runtime.log_outcome(
        ToolOutcome(
            name="memory_search",
            args={"query": "architecture"},
            result="one match",
        )
    )

    [event] = captured
    payload = RuntimeLogEventPayload.from_mapping(event.payload)
    assert payload.metadata == {
        "service_component": "memory",
        "operation": "memory_search",
    }
