"""Approval declaration, suspension protocol, and bound interpreter."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from nuself.runtime.event.payload import RuntimeLogEventPayload
from nuself.runtime.feature.effect import (
    BoundFeatureEffect,
    EffectEnvironment,
    ExecutionConstraint,
    FeatureEffect,
    FeatureEffectRejected,
    FeatureInvocation,
)
from nuself.runtime.feature.protocol import (
    ToolEffectRequest,
    ToolEffectResolution,
    ToolEffectRequired,
)

type ApprovalRisk = Literal["reversible", "destructive", "external"]
type ApprovalInput = Literal[
    "affirmative",
    "declined",
    "eof",
    "interrupt",
    "unavailable",
]
type SummaryBuilder = Callable[[tuple[object, ...], dict[str, object]], str]


@dataclass(frozen=True)
class ApprovalEffectRequest(ToolEffectRequest):
    """One approval interaction emitted before a Tool service call."""

    action: str
    resource: str
    risk: ApprovalRisk
    summary: str

    def __post_init__(self) -> None:
        super().__post_init__()
        if not self.action.strip():
            raise ValueError("approval action must not be blank")
        if not self.resource.strip():
            raise ValueError("approval resource must not be blank")
        if not self.summary.strip():
            raise ValueError("approval summary must not be blank")

    @property
    def kind(self) -> str:
        return "approval"


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
                raise ValueError("approved decision requires an approver")
        elif self.input_kind == "affirmative":
            raise ValueError(
                "declined decision cannot have affirmative input"
            )


@dataclass(frozen=True)
class ApprovalEffectResolution(ToolEffectResolution):
    """Approval decision exactly bound to its request."""

    decision: ApprovalEffectDecision

    def __post_init__(self) -> None:
        if not isinstance(self.request, ApprovalEffectRequest):
            raise TypeError(
                "approval resolution requires an approval request"
            )

    @property
    def kind(self) -> str:
        return "approval"


@dataclass(frozen=True)
class ApprovalEffect(FeatureEffect, ExecutionConstraint):
    """Immutable declaration of a pre-execution approval gate."""

    cardinality_key = "interaction.approval"

    action: str
    resource: str
    risk: ApprovalRisk = "reversible"
    summary: SummaryBuilder | None = None

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError("confirmation action must not be blank")
        if not self.resource.strip():
            raise ValueError("confirmation resource must not be blank")

    def bind(self, environment: EffectEnvironment) -> BoundFeatureEffect:
        return _BoundApprovalEffect(self, environment)

    def validate_execution(self, execution: str | None) -> None:
        if execution == "readonly":
            raise ValueError("readonly feature cannot require confirmation")


class _BoundApprovalEffect(BoundFeatureEffect):
    before_priority = 10

    def __init__(
        self,
        declaration: ApprovalEffect,
        environment: EffectEnvironment,
    ) -> None:
        self._declaration = declaration
        self._environment = environment

    def before(self, invocation: FeatureInvocation) -> None:
        declaration = self._declaration
        summary = (
            declaration.summary(invocation.args, dict(invocation.kwargs))
            if declaration.summary is not None
            else f"{declaration.action} {declaration.resource}"
        )
        request = ApprovalEffectRequest(
            component=invocation.component,
            operation=invocation.operation,
            action=declaration.action,
            resource=declaration.resource,
            risk=declaration.risk,
            summary=summary,
        )
        resolution = self._environment.effect_port.resolve(
            request,
            on_requested=lambda: self._publish(
                invocation,
                "approval_requested",
                "pending",
                {
                    "action": declaration.action,
                    "resource": declaration.resource,
                    "risk": declaration.risk,
                    "summary": summary,
                },
            ),
        )
        if resolution.request != request:
            raise ToolEffectRequired(request)
        if not isinstance(resolution, ApprovalEffectResolution):
            raise TypeError("approval request received an invalid resolution")
        decision = resolution.decision
        self._publish(
            invocation,
            "approval_decided",
            "decided",
            {
                "approved": decision.approved,
                "approver": decision.approver,
                "input_kind": decision.input_kind,
            },
        )
        if not decision.approved and decision.input_kind == "unavailable":
            raise ToolEffectRequired(request)
        if not decision.approved:
            raise FeatureEffectRejected(
                "Action was not approved; no changes were made."
            )

    def _publish(
        self,
        invocation: FeatureInvocation,
        frontend_event: str,
        status: str,
        fields: dict[str, object],
    ) -> None:
        events = self._environment.events
        if events is None:
            return
        try:
            events.publish(
                producer=self._environment.producer,
                name="tool.activity",
                payload=RuntimeLogEventPayload(
                    message=(
                        "Approval requested"
                        if frontend_event == "approval_requested"
                        else "Approval decided"
                    ) + f" for {invocation.operation}",
                    level="info",
                    status=status,
                    metadata={
                        "frontend_event": frontend_event,
                        "service_component": invocation.component,
                        "operation": invocation.operation,
                        **fields,
                    },
                ).to_mapping(),
            )
        except Exception:
            return
