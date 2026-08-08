"""Orthogonal declarations for application feature functions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import overload

from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.feature.approval import (
    ApprovalEffect,
    ApprovalRisk,
    SummaryBuilder,
)
from nuself.runtime.feature.audit import AuditEffect
from nuself.runtime.feature.effect import (
    Execution,
    ExecutionConstraint,
    FeatureEffect,
)
from nuself.runtime.feature.observation import ObservationEffect

_SPEC_ATTRIBUTE = "__nuself_feature_spec__"


class FeaturePolicyConflictError(ValueError):
    """Raised when orthogonal declarations contradict each other."""


@dataclass(frozen=True)
class ToolPolicy:
    """Framework-facing identity for one feature function."""

    name: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class CompactPolicy:
    """Marker for intentionally compact observation presentation."""


@dataclass(frozen=True)
class FeatureSpec:
    """Immutable policy set attached to a normal Python callable."""

    tool: ToolPolicy | None = None
    component: str | None = None
    execution: Execution | None = None
    effects: tuple[FeatureEffect, ...] = ()
    compact: CompactPolicy | None = None


type FeatureCallable[**P, R] = Callable[P, R]


def feature_spec(function: Callable[..., object]) -> FeatureSpec:
    """Return a function's declarations, or an empty specification."""

    value = getattr(function, _SPEC_ATTRIBUTE, None)
    return value if isinstance(value, FeatureSpec) else FeatureSpec()


def _attach[**P, R](
    function: FeatureCallable[P, R],
    **changes: object,
) -> FeatureCallable[P, R]:
    current = feature_spec(function)
    updated = replace(current, **changes)
    _validate(updated)
    setattr(function, _SPEC_ATTRIBUTE, updated)
    return function


def _validate(spec: FeatureSpec) -> None:
    if spec.component is not None and not spec.component.strip():
        raise ValueError("feature component must not be blank")
    cardinality = tuple(
        effect.cardinality_key
        for effect in spec.effects
        if effect.cardinality_key is not None
    )
    if len(cardinality) != len(set(cardinality)):
        raise FeaturePolicyConflictError(
            "unique feature effects may be declared only once"
        )
    for declaration in spec.effects:
        if not isinstance(declaration, ExecutionConstraint):
            continue
        try:
            declaration.validate_execution(spec.execution)
        except ValueError as exc:
            raise FeaturePolicyConflictError(
                diagnostic_exception_message(exc)
            ) from exc


def _append_effect[**P, R](
    target: FeatureCallable[P, R],
    effect: FeatureEffect,
) -> FeatureCallable[P, R]:
    return _attach(
        target,
        effects=(*feature_spec(target).effects, effect),
    )


def effect[**P, R](
    declaration: FeatureEffect,
) -> Callable[[FeatureCallable[P, R]], FeatureCallable[P, R]]:
    """Attach one immutable effect declaration without executing it."""

    def decorate(target: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
        return _append_effect(target, declaration)

    return decorate


@overload
def tool[**P, R](function: FeatureCallable[P, R]) -> FeatureCallable[P, R]: ...


@overload
def tool[**P, R](
    function: None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Callable[[FeatureCallable[P, R]], FeatureCallable[P, R]]: ...


def tool[**P, R](
    function: FeatureCallable[P, R] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> (
    FeatureCallable[P, R]
    | Callable[[FeatureCallable[P, R]], FeatureCallable[P, R]]
):
    """Declare that a feature is materialized as a framework-native tool."""

    if name is not None and not name.strip():
        raise ValueError("tool name must not be blank")
    if description is not None and not description.strip():
        raise ValueError("tool description must not be blank")

    def decorate(target: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
        return _attach(
            target,
            tool=ToolPolicy(name=name, description=description),
        )

    return decorate(function) if function is not None else decorate


def component[**P, R](
    name: str,
) -> Callable[[FeatureCallable[P, R]], FeatureCallable[P, R]]:
    """Declare feature ownership without changing execution."""

    if not name.strip():
        raise ValueError("feature component must not be blank")

    def decorate(target: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
        return _attach(target, component=name)

    return decorate


def readonly[**P, R](
    function: FeatureCallable[P, R],
) -> FeatureCallable[P, R]:
    """Declare a side-effect-free feature."""

    current = feature_spec(function)
    if current.execution == "mutating":
        raise FeaturePolicyConflictError(
            "feature cannot be both readonly and mutating"
        )
    return _attach(function, execution="readonly")


def mutating[**P, R](
    function: FeatureCallable[P, R],
) -> FeatureCallable[P, R]:
    """Declare a state-changing feature."""

    current = feature_spec(function)
    if current.execution == "readonly":
        raise FeaturePolicyConflictError(
            "feature cannot be both readonly and mutating"
        )
    return _attach(function, execution="mutating")


def confirmed[**P, R](
    *,
    action: str,
    resource: str,
    risk: ApprovalRisk = "reversible",
    summary: SummaryBuilder | None = None,
) -> Callable[[FeatureCallable[P, R]], FeatureCallable[P, R]]:
    """Declare confirmation gating without selecting a frontend."""

    policy = ApprovalEffect(
        action=action,
        resource=resource,
        risk=risk,
        summary=summary,
    )

    def decorate(target: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
        return effect(policy)(target)

    return decorate


@overload
def observed[**P, R](function: FeatureCallable[P, R]) -> FeatureCallable[P, R]: ...


@overload
def observed[**P, R](
    function: None = None,
) -> Callable[[FeatureCallable[P, R]], FeatureCallable[P, R]]: ...


def observed[**P, R](
    function: FeatureCallable[P, R] | None = None,
) -> (
    FeatureCallable[P, R]
    | Callable[[FeatureCallable[P, R]], FeatureCallable[P, R]]
):
    """Declare safe lifecycle observation."""

    def decorate(target: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
        return effect(ObservationEffect())(target)

    return decorate(function) if function is not None else decorate


def compact[**P, R](function: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
    """Declare operation/status-only presentation for observed outcomes."""

    return _attach(function, compact=CompactPolicy())


def audited[**P, R](
    event: str,
) -> Callable[[FeatureCallable[P, R]], FeatureCallable[P, R]]:
    """Declare one stable audit identity."""

    policy = AuditEffect(event)

    def decorate(target: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
        return effect(policy)(target)

    return decorate


def require_tool_spec(function: Callable[..., object]) -> FeatureSpec:
    """Return a complete tool spec or fail at composition."""

    spec = feature_spec(function)
    if spec.tool is None:
        raise ValueError("feature function is not declared as a tool")
    if spec.component is None:
        raise ValueError("tool feature requires a component")
    if spec.execution is None:
        raise ValueError("tool feature requires an execution declaration")
    for declaration in spec.effects:
        if isinstance(declaration, ExecutionConstraint):
            declaration.validate_execution(spec.execution)
    return spec
