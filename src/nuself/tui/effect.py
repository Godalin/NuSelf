"""Terminal router for structured Tool effects."""

from __future__ import annotations

from nuself.runtime.feature.effect import (
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
    ) -> ToolEffectResolution:
        decision = TerminalApprovalPort().request(request)
        return ToolEffectResolution(request, decision)
