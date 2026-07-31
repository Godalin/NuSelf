"""Frontend-neutral interaction events and approval ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


@dataclass(frozen=True)
class ApprovalRequest:
    """Frontend-neutral request for one explicit decision."""

    component: str
    operation: str
    action: str
    resource: str
    risk: Literal["reversible", "destructive", "external"]
    summary: str


@dataclass(frozen=True)
class ApprovalDecision:
    """One frontend decision."""

    approved: bool
    approver: str | None = None
    input_kind: Literal[
        "affirmative",
        "declined",
        "eof",
        "interrupt",
        "unavailable",
    ] = "unavailable"

    def __post_init__(self) -> None:
        if self.approved:
            if self.input_kind != "affirmative":
                raise ValueError(
                    "approved decision requires affirmative input"
                )
            if self.approver is None or not self.approver.strip():
                raise ValueError(
                    "approved decision requires an approver"
                )
        elif self.input_kind == "affirmative":
            raise ValueError(
                "declined decision cannot have affirmative input"
            )


class ApprovalPort(Protocol):
    """Replaceable interaction boundary for confirmation."""

    def request(self, request: ApprovalRequest) -> ApprovalDecision: ...


class RejectUnavailableApprovalPort:
    """Safe adapter for a backend without an interactive frontend."""

    def request(self, request: ApprovalRequest) -> ApprovalDecision:
        del request
        return ApprovalDecision(False, input_kind="unavailable")
