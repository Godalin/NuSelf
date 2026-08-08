"""End-to-end contract for structured Tool activity presentation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from langchain_core.messages import ToolMessage
from langgraph.prebuilt.tool_node import ToolCallRequest

from nuself.agent.middleware import ToolCaptureMiddleware
from nuself.agent.projection import LogToolOutcomeProjection
from nuself.agent.tools.decorated import materialize_tool
from nuself.cli.repl.activity import visible_interactive_activity_events
from nuself.daemon.activity import ActivityBroker
from nuself.daemon.payloads import ActivityEventsResponsePayload
from nuself.decorators import component, observed, readonly, tool
from nuself.runtime.context import runtime_context
from nuself.runtime.feature.execution import FeatureExecutor
from nuself.tui.render import render_log_event


def test_decorated_tool_survives_delivery_and_tui_rendering(
    tmp_path: Path,
) -> None:
    @tool(name="memory_search", description="Search durable memories.")
    @component("memory")
    @readonly
    @observed
    def search(query: str) -> str:
        return f'Found memory for "{query}"'

    framework_tool = materialize_tool(search, executor=FeatureExecutor())
    broker = ActivityBroker()
    subscription_id = broker.open("turn-1")
    middleware = ToolCaptureMiddleware(
        outcomes=LogToolOutcomeProjection(
            component="chat",
            project_root=tmp_path,
            activity_sink=broker.publish,
        )
    )
    request = ToolCallRequest(
        tool_call=cast(Any, {
            "name": framework_tool.name,
            "args": {"query": "architecture"},
            "id": "call-1",
            "type": "tool_call",
        }),
        tool=framework_tool,
        state={},
        runtime=cast(Any, None),
    )

    def invoke_tool(call: ToolCallRequest) -> ToolMessage:
        result = framework_tool.invoke(call.tool_call["args"])
        return ToolMessage(
            content=str(result),
            name=framework_tool.name,
            tool_call_id=call.tool_call["id"] or "",
        )

    with runtime_context(turn_id="turn-1", conversation_id="default"):
        middleware.wrap_tool_call(request, invoke_tool)

    batch = broker.next_events(
        subscription_id,
        timeout_seconds=0,
        limit=10,
    )
    transported = ActivityEventsResponsePayload.from_wire(
        ActivityEventsResponsePayload(batch.events).to_wire()
    )
    visible = visible_interactive_activity_events(list(transported.events))

    assert len(visible) == 1
    assert render_log_event(visible[0], color=False).splitlines() == [
        "[chat] [memory] service_tool_called tool=memory_search "
        "status=completed conversation=default turn=turn-1",
        "  args: {",
        '    "query": "architecture"',
        "  }",
        "  result:",
        '    Found memory for "architecture"',
    ]
