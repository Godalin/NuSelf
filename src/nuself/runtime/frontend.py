"""Frontend-neutral interaction events and approval ports."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
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


@dataclass(frozen=True)
class ApprovalGrant:
    """One frontend decision bound to the exact request it answered."""

    request: ApprovalRequest
    decision: ApprovalDecision


class ApprovalRequired(Exception):
    """Execution paused because the active frontend must decide."""

    def __init__(self, request: ApprovalRequest) -> None:
        super().__init__(
            f"frontend approval required for {request.operation}"
        )
        self.request = request


_CURRENT_APPROVAL_GRANT: ContextVar[ApprovalGrant | None] = ContextVar(
    "nuself_approval_grant",
    default=None,
)


@contextmanager
def use_approval_grant(
    grant: ApprovalGrant | None,
) -> Generator[None, None, None]:
    """Install one request-scoped approval grant."""

    token: Token[ApprovalGrant | None] = _CURRENT_APPROVAL_GRANT.set(grant)
    try:
        yield
    finally:
        _CURRENT_APPROVAL_GRANT.reset(token)


class RequestApprovalPort:
    """Resolve approval from the current cross-process request context."""

    def request(self, request: ApprovalRequest) -> ApprovalDecision:
        grant = _CURRENT_APPROVAL_GRANT.get()
        if grant is None or grant.request != request:
            raise ApprovalRequired(request)
        return grant.decision


class RejectUnavailableApprovalPort:
    """Safe adapter for a backend without an interactive frontend."""

    def request(self, request: ApprovalRequest) -> ApprovalDecision:
        del request
        return ApprovalDecision(False, input_kind="unavailable")
