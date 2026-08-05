"""LangGraph adapter for structured Tool effects."""

from __future__ import annotations

from langgraph.types import interrupt

from nuself.runtime.feature.effect import (
    ToolEffectPort,
    ToolEffectRequest,
    ToolEffectRequired,
    ToolEffectResolution,
)


class GraphToolEffectPort(ToolEffectPort):
    """Suspend the active graph and resume with an exact resolution."""

    def resolve(
        self,
        request: ToolEffectRequest,
    ) -> ToolEffectResolution:
        try:
            resolution = interrupt(request)
        except RuntimeError as exc:
            raise ToolEffectRequired(request) from exc
        if not isinstance(resolution, ToolEffectResolution):
            raise TypeError(
                "Tool effect checkpoint resumed without a typed resolution"
            )
        if resolution.request != request:
            raise ToolEffectRequired(request)
        return resolution
