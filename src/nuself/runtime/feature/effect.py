"""Structured requests and resolutions emitted by Tool effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

type ToolEffectKind = Literal["approval"]
type ApprovalRisk = Literal["reversible", "destructive", "external"]
type ApprovalInput = Literal[
    "affirmative",
    "declined",
    "eof",
    "interrupt",
    "unavailable",
]


@dataclass(frozen=True)
class ApprovalEffectRequest:
    """One approval interaction emitted before a Tool service call."""

    component: str
    operation: str
    action: str
    resource: str
    risk: ApprovalRisk
    summary: str
    kind: Literal["approval"] = "approval"


type ToolEffectRequest = ApprovalEffectRequest


@dataclass(frozen=True)
class ApprovalEffectDecision:
    """Frontend decision for an approval interaction."""

    approved: bool
    approver: str | None = None
    input_kind: ApprovalInput = "unavailable"

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


type ToolEffectDecision = ApprovalEffectDecision


@dataclass(frozen=True)
class ToolEffectResolution:
    """One frontend decision exactly bound to its effect request."""

    request: ToolEffectRequest
    decision: ToolEffectDecision


class ToolEffectPort(Protocol):
    """Resolve a structured Tool effect through one runtime adapter."""

    def resolve(
        self,
        request: ToolEffectRequest,
    ) -> ToolEffectResolution: ...


class ToolEffectRequired(Exception):
    """Execution suspended until a frontend resolves one Tool effect."""

    def __init__(self, request: ToolEffectRequest) -> None:
        super().__init__(
            f"frontend effect resolution required for {request.operation}"
        )
        self.request = request


class RejectUnavailableEffectPort:
    """Safe adapter for a runtime without an interactive frontend."""

    def resolve(
        self,
        request: ToolEffectRequest,
    ) -> ToolEffectResolution:
        return ToolEffectResolution(
            request,
            ApprovalEffectDecision(False, input_kind="unavailable"),
        )
