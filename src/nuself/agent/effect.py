"""LangGraph adapter for structured Tool effects."""

from __future__ import annotations

from collections.abc import Callable

from langgraph.errors import GraphInterrupt
from langgraph.types import interrupt

from nuself.runtime.feature.protocol import (
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
        *,
        on_requested: Callable[[], None],
    ) -> ToolEffectResolution:
        try:
            resolution = interrupt(request)
        except GraphInterrupt:
            on_requested()
            raise
        except RuntimeError as exc:
            on_requested()
            raise ToolEffectRequired(request) from exc
        if not isinstance(resolution, ToolEffectResolution):
            raise TypeError(
                "Tool effect checkpoint resumed without a typed resolution"
            )
        if resolution.request != request:
            raise ToolEffectRequired(request)
        return resolution
