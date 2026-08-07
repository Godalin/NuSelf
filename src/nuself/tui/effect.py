"""Terminal router for structured Tool effects."""

from __future__ import annotations

from collections.abc import Callable

from nuself.runtime.feature.approval import (
    ApprovalEffectRequest,
    ApprovalEffectResolution,
)
from nuself.runtime.feature.protocol import (
    ToolEffectPort,
    ToolEffectRequest,
    ToolEffectResolution,
)
from nuself.tui.approval import TerminalApprovalPort


class TerminalToolEffectPort(ToolEffectPort):
    """Resolve each supported Tool effect on the terminal owner thread."""

    def resolve(
        self,
        request: ToolEffectRequest,
        *,
        on_requested: Callable[[], None],
    ) -> ToolEffectResolution:
        match request:
            case ApprovalEffectRequest():
                on_requested()
                decision = TerminalApprovalPort().request(request)
                return ApprovalEffectResolution(request, decision)
            case _:
                raise TypeError(
                    "terminal does not support Tool effect request "
                    f"{type(request).__name__}"
                )
