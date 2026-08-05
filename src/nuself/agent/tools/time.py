"""Runtime-owned current-time tool definition."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from langchain_core.tools import BaseTool

from nuself.agent.tools.decorated import materialize_tool
from nuself.decorators import component, observed, readonly, tool
from nuself.runtime.clock import utc_now
from nuself.runtime.feature.execution import FeatureExecutor


def build_time_tools(
    *,
    executor: FeatureExecutor,
    clock: Callable[[], datetime] = utc_now,
) -> tuple[BaseTool, ...]:
    """Build the current-time query Tool from an injected clock."""

    @tool(
        name="runtime_time",
        description=(
            "Return the current time in the host's local timezone and UTC. "
            "Use when the answer depends on now, today, or relative dates."
        ),
    )
    @component("runtime")
    @readonly
    @observed
    def current_time() -> str:
        """Return one current instant in local time and UTC."""

        instant = clock()
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("runtime clock must return an aware datetime")
        return (
            f"Local time: {instant.astimezone().isoformat()}\n"
            f"UTC time: {instant.astimezone(UTC).isoformat()}"
        )

    return (materialize_tool(current_time, executor=executor),)
