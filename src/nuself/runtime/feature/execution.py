"""Interpret composable Tool effects through injected runtime ports."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from langchain_core.tools import ToolException

from nuself.runtime.event.payload import RuntimeLogEventPayload
from nuself.runtime.event.publisher import EventPublisher
from nuself.runtime.feature.effect import (
    ApprovalEffectRequest,
    RejectUnavailableEffectPort,
    ToolEffectPort,
    ToolEffectRequired,
)
from nuself.runtime.feature.policy import (
    ApprovalEffectPolicy,
    AuditEffectPolicy,
    FeatureEffectPolicy,
    ObservationEffectPolicy,
    feature_spec,
)


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


class ToolEffectDeclined(ToolException):
    """A frontend declined a suspending Tool effect."""


@dataclass(frozen=True)
class ToolInvocation:
    """Safe execution context shared with effect handlers."""

    component: str
    operation: str
    args: tuple[object, ...]
    kwargs: dict[str, object]


class ToolEffectHandler(Protocol):
    """Interpret one declarative effect at Tool lifecycle phases."""

    @property
    def policy_type(self) -> type[object]: ...

    def before(
        self,
        policy: FeatureEffectPolicy,
        invocation: ToolInvocation,
    ) -> None: ...

    def after(
        self,
        policy: FeatureEffectPolicy,
        invocation: ToolInvocation,
        error: Exception | None,
    ) -> None: ...


class ApprovalEffectHandler:
    """Resolve approval before the service function is called."""

    policy_type = ApprovalEffectPolicy

    def __init__(
        self,
        effects: ToolEffectPort,
        events: EventPublisher | None,
    ) -> None:
        self._effects = effects
        self._events = events

    def before(
        self,
        policy: FeatureEffectPolicy,
        invocation: ToolInvocation,
    ) -> None:
        assert isinstance(policy, ApprovalEffectPolicy)
        summary = (
            policy.summary(invocation.args, invocation.kwargs)
            if policy.summary is not None
            else f"{policy.action} {policy.resource}"
        )
        request = ApprovalEffectRequest(
            component=invocation.component,
            operation=invocation.operation,
            action=policy.action,
            resource=policy.resource,
            risk=policy.risk,
            summary=summary,
        )
        resolution = self._effects.resolve(request)
        if resolution.request != request:
            raise ToolEffectRequired(request)
        self._publish("approval_requested", invocation, {
            "action": policy.action,
            "resource": policy.resource,
            "risk": policy.risk,
            "summary": summary,
        })
        decision = resolution.decision
        self._publish("approval_decided", invocation, {
            "approved": decision.approved,
            "approver": decision.approver,
            "input_kind": decision.input_kind,
        })
        if not decision.approved and decision.input_kind == "unavailable":
            raise ToolEffectRequired(request)
        if not decision.approved:
            raise ToolEffectDeclined(
                f"{invocation.operation} effect was declined"
            )

    def after(
        self,
        policy: FeatureEffectPolicy,
        invocation: ToolInvocation,
        error: Exception | None,
    ) -> None:
        del policy, invocation, error

    def _publish(
        self,
        kind: str,
        invocation: ToolInvocation,
        fields: dict[str, object],
    ) -> None:
        if self._events is None:
            return
        try:
            self._events.publish(
                producer="chat",
                name="tool.activity",
                payload=RuntimeLogEventPayload(
                    message=(
                        "Approval requested"
                        if kind == "approval_requested"
                        else "Approval decided"
                    ) + f" for {invocation.operation}",
                    level="info",
                    status="pending" if kind == "approval_requested" else "decided",
                    metadata={
                        "frontend_event": kind,
                        "service_component": invocation.component,
                        "operation": invocation.operation,
                        **fields,
                    },
                ).to_mapping(),
            )
        except Exception:
            return


class ObservationEffectHandler:
    """Project a privacy-safe Tool lifecycle."""

    policy_type = ObservationEffectPolicy

    def __init__(self, events: EventPublisher | None) -> None:
        self._events = events

    def before(
        self,
        policy: FeatureEffectPolicy,
        invocation: ToolInvocation,
    ) -> None:
        del policy
        self._publish(invocation, "started", None)

    def after(
        self,
        policy: FeatureEffectPolicy,
        invocation: ToolInvocation,
        error: Exception | None,
    ) -> None:
        del policy
        self._publish(
            invocation,
            "failed" if error is not None else "completed",
            error,
        )

    def _publish(
        self,
        invocation: ToolInvocation,
        outcome: str,
        error: Exception | None,
    ) -> None:
        if self._events is None:
            return
        try:
            self._events.publish(
                producer="chat",
                name=f"feature.{outcome}",
                payload=RuntimeLogEventPayload(
                    message=f"feature {outcome}: {invocation.operation}",
                    level="error" if error is not None else "info",
                    status=outcome,
                    metadata={
                        "service_component": invocation.component,
                        "operation": invocation.operation,
                        **(
                            {"error_type": type(error).__name__}
                            if error is not None
                            else {}
                        ),
                    },
                ).to_mapping(),
            )
        except Exception:
            return


class AuditEffectHandler:
    """Project a stable domain audit after execution."""

    policy_type = AuditEffectPolicy

    def __init__(self, audits: FeatureAuditSink | None) -> None:
        self._audits = audits

    def before(
        self,
        policy: FeatureEffectPolicy,
        invocation: ToolInvocation,
    ) -> None:
        del policy, invocation

    def after(
        self,
        policy: FeatureEffectPolicy,
        invocation: ToolInvocation,
        error: Exception | None,
    ) -> None:
        assert isinstance(policy, AuditEffectPolicy)
        if self._audits is None:
            return
        try:
            self._audits.write(FeatureAuditRecord(
                component=invocation.component,
                event=policy.event,
                operation=invocation.operation,
                outcome="failed" if error is not None else "completed",
                error_type=type(error).__name__ if error is not None else None,
            ))
        except Exception:
            return


class ToolEffectInterpreter:
    """Dispatch canonical Tool effects to independent lifecycle handlers."""

    def __init__(self, handlers: tuple[ToolEffectHandler, ...]) -> None:
        self._handlers = {handler.policy_type: handler for handler in handlers}

    def before(
        self,
        effects: tuple[FeatureEffectPolicy, ...],
        invocation: ToolInvocation,
    ) -> None:
        for policy in effects:
            self._handler(policy).before(policy, invocation)

    def after(
        self,
        effects: tuple[FeatureEffectPolicy, ...],
        invocation: ToolInvocation,
        error: Exception | None,
    ) -> None:
        for policy in effects:
            self._handler(policy).after(policy, invocation, error)

    def _handler(self, policy: FeatureEffectPolicy) -> ToolEffectHandler:
        try:
            return self._handlers[type(policy)]
        except KeyError as exc:
            raise TypeError(
                f"no Tool effect handler for {type(policy).__name__}"
            ) from exc


class FeatureExecutor:
    """Invoke a feature through one composable Tool effect interpreter."""

    def __init__(
        self,
        *,
        effects: ToolEffectPort | None = None,
        events: EventPublisher | None = None,
        audits: FeatureAuditSink | None = None,
    ) -> None:
        self._interpreter = ToolEffectInterpreter((
            ApprovalEffectHandler(effects or RejectUnavailableEffectPort(), events),
            ObservationEffectHandler(events),
            AuditEffectHandler(audits),
        ))

    def invoke[**P, R](
        self,
        function: Callable[P, R],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> R:
        spec = feature_spec(function)
        invocation = ToolInvocation(
            component=spec.component or "runtime",
            operation=(
                spec.tool.name
                if spec.tool is not None and spec.tool.name is not None
                else function.__name__
            ),
            args=args,
            kwargs=dict(kwargs),
        )
        self._interpreter.before(spec.effects, invocation)
        try:
            result = function(*args, **kwargs)
        except Exception as exc:
            self._interpreter.after(spec.effects, invocation, exc)
            raise
        self._interpreter.after(spec.effects, invocation, None)
        return result
