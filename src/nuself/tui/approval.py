"""Terminal adapter for the frontend-neutral approval port."""

from __future__ import annotations

import getpass

from nuself.runtime.frontend import (
    ApprovalDecision,
    ApprovalRequest,
)
from nuself.tui.render import render_approval_prompt


class TerminalApprovalPort:
    """Request one safe-default decision from the active terminal."""

    def request(self, request: ApprovalRequest) -> ApprovalDecision:
        prompt = render_approval_prompt(
            request.component,  # pyright: ignore[reportArgumentType]
            request.summary,
            tool=request.operation,
        )
        print(prompt, flush=True)
        print("approve? [y/N] ", end="", flush=True)
        try:
            response = input()
        except EOFError:
            print()
            return ApprovalDecision(False, input_kind="eof")
        except KeyboardInterrupt:
            print()
            return ApprovalDecision(False, input_kind="interrupt")
        if response.strip().lower() not in {"y", "yes"}:
            return ApprovalDecision(False, input_kind="declined")
        return ApprovalDecision(
            True,
            approver=getpass.getuser(),
            input_kind="affirmative",
        )
