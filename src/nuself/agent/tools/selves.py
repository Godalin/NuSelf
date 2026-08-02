"""Selves-owned framework tool definitions."""

from __future__ import annotations

from collections.abc import Callable

from langchain_core.tools import BaseTool

from nuself.agent.tools.decorated import materialize_tool
from nuself.decorators import component, observed, readonly, tool
from nuself.runtime.feature.execution import FeatureExecutor


def build_selves_tools(
    consult: Callable[[str, str, str | None], str] | None,
    *,
    executor: FeatureExecutor | None = None,
) -> tuple[BaseTool, ...]:
    """Build the optional selves consultation tool."""
    if consult is None:
        return ()

    @tool(
        name="selves_consult",
        description=(
            "Invoke NuSelf's internal multi-persona subagent for perspective synthesis. "
            "Use for explicit multi-perspective requests, complex design tradeoffs, value conflicts, "
            "emotionally loaded reflection, self-model questions, or when the user asks for inner discussion. "
            "Do not use for direct service status/count/search questions."
        ),
    )
    @component("selves")
    @readonly
    @observed
    def consult_selves(
        topic: str,
        mode: str = "consult",
        context: str | None = None,
    ) -> str:
        """Invoke NuSelf's internal multi-persona subagent for perspective synthesis."""
        topic_str = str(topic) if topic else ""
        if not topic_str.strip():
            return "Error: topic must be a non-empty string"
        mode_str = str(mode) if mode else "consult"
        context_str = str(context) if context is not None else None
        return consult(
            topic_str.strip(),
            mode_str.strip() or "consult",
            context_str,
        )

    return (
        materialize_tool(
            consult_selves,
            executor=executor or FeatureExecutor(),
        ),
    )
