"""Frontend-neutral interaction events and approval ports."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Protocol

FrontendEventKind = Literal[
    "approval_requested",
    "approval_decided",
]


@dataclass(frozen=True)
class FrontendEvent:
    """One payload-safe presentation event."""

    kind: FrontendEventKind
    component: str
    operation: str
    fields: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        if not self.component.strip():
            raise ValueError("frontend event component must not be blank")
        if not self.operation.strip():
            raise ValueError("frontend event operation must not be blank")
        object.__setattr__(
            self,
            "fields",
            MappingProxyType(dict(self.fields)),
        )


class FrontendEventSink(Protocol):
    """Presentation adapter boundary."""

    def publish(self, event: FrontendEvent) -> None: ...


class NullFrontendEventSink:
    """Frontend sink for non-interactive execution."""

    def publish(self, event: FrontendEvent) -> None:
        del event


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
