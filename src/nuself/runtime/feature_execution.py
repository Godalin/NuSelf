"""Execution of orthogonal feature policies through injected ports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import ParamSpec, Protocol, TypeVar

from langchain_core.tools import ToolException

from nuself.runtime.features import FeatureSpec, feature_spec
from nuself.runtime.frontend import (
    ApprovalPort,
    ApprovalRequest,
    FrontendEvent,
    FrontendEventSink,
    NullFrontendEventSink,
    RejectUnavailableApprovalPort,
)

P = ParamSpec("P")
R = TypeVar("R")


@dataclass(frozen=True)
class FeatureAuditRecord:
    """Payload-safe outcome for a declared domain audit."""

    component: str
    event: str
    operation: str
    outcome: str
    error_type: str | None = None


class FeatureAuditSink(Protocol):
    """Durable audit adapter boundary."""

    def write(self, record: FeatureAuditRecord) -> None: ...


class NullFeatureAuditSink:
    def write(self, record: FeatureAuditRecord) -> None:
        del record


class FeatureConfirmationDeclined(ToolException):
    """A frontend did not approve a declared operation."""


class FeatureExecutor:
    """Interpret feature policies without owning presentation."""

    def __init__(
        self,
        *,
        approvals: ApprovalPort | None = None,
        events: FrontendEventSink | None = None,
        audits: FeatureAuditSink | None = None,
    ) -> None:
        self._approvals = approvals or RejectUnavailableApprovalPort()
        self._events = events or NullFrontendEventSink()
        self._audits = audits or NullFeatureAuditSink()

    def invoke(
        self,
        function: Callable[P, R],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        spec = feature_spec(function)
        component = spec.component or "runtime"
        operation = (
            spec.tool.name
            if spec.tool is not None and spec.tool.name is not None
            else function.__name__
        )
        self._confirm(spec, component, operation, args, kwargs)
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            self._audit(spec, component, operation, "failed", exc)
            raise
        self._audit(spec, component, operation, "completed", None)
        return result

    def _confirm(
        self,
        spec: FeatureSpec,
        component: str,
        operation: str,
        args: tuple[object, ...],
        kwargs: dict[str, object],
    ) -> None:
        policy = spec.confirmation
        if policy is None:
            return
        summary = (
            policy.summary(args, kwargs)
            if policy.summary is not None
            else f"{policy.action} {policy.resource}"
        )
        request = ApprovalRequest(
            component=component,
            operation=operation,
            action=policy.action,
            resource=policy.resource,
            risk=policy.risk,
            summary=summary,
        )
        self._publish_secondary(
            FrontendEvent(
                "approval_requested",
                component,
                operation,
                {
                    "action": policy.action,
                    "resource": policy.resource,
                    "risk": policy.risk,
                    "summary": summary,
                },
            )
        )
        decision = self._approvals.request(request)
        self._publish_secondary(
            FrontendEvent(
                "approval_decided",
                component,
                operation,
                {
                    "approved": decision.approved,
                    "approver": decision.approver,
                    "input_kind": decision.input_kind,
                },
            )
        )
        if not decision.approved:
            raise FeatureConfirmationDeclined(
                f"{operation} was not approved"
            )

    def _publish_secondary(self, event: FrontendEvent) -> None:
        try:
            self._events.publish(event)
        except Exception:
            # Frontend observation is never authority for the operation.
            return

    def _audit(
        self,
        spec: FeatureSpec,
        component: str,
        operation: str,
        outcome: str,
        error: Exception | None,
    ) -> None:
        if spec.audit is None:
            return
        try:
            self._audits.write(
                FeatureAuditRecord(
                    component=component,
                    event=spec.audit.event,
                    operation=operation,
                    outcome=outcome,
                    error_type=type(error).__name__ if error else None,
                )
            )
        except Exception:
            # Durable audit projection is secondary to the declared operation.
            return
