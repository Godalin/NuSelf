"""Orthogonal declarations for application feature functions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal, overload

from nuself.runtime.feature.effect import ApprovalRisk

type Execution = Literal["readonly", "mutating"]
type SummaryBuilder = Callable[[tuple[object, ...], dict[str, object]], str]

_SPEC_ATTRIBUTE = "__nuself_feature_spec__"


class FeaturePolicyConflictError(ValueError):
    """Raised when orthogonal declarations contradict each other."""


@dataclass(frozen=True)
class ToolPolicy:
    """Framework-facing identity for one feature function."""

    name: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class ApprovalEffectPolicy:
    """Declarative approval interaction effect."""

    action: str
    resource: str
    risk: ApprovalRisk = "reversible"
    summary: SummaryBuilder | None = None

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError("confirmation action must not be blank")
        if not self.resource.strip():
            raise ValueError("confirmation resource must not be blank")


@dataclass(frozen=True)
class ObservationEffectPolicy:
    """Privacy-safe lifecycle projection effect."""


@dataclass(frozen=True)
class CompactPolicy:
    """Marker for intentionally compact observation presentation."""


@dataclass(frozen=True)
class AuditEffectPolicy:
    """Stable domain audit projection effect."""

    event: str

    def __post_init__(self) -> None:
        if not self.event.strip():
            raise ValueError("audit event must not be blank")


type FeatureEffectPolicy = (
    ApprovalEffectPolicy | ObservationEffectPolicy | AuditEffectPolicy
)


@dataclass(frozen=True)
class FeatureSpec:
    """Immutable policy set attached to a normal Python callable."""

    tool: ToolPolicy | None = None
    component: str | None = None
    execution: Execution | None = None
    effects: tuple[FeatureEffectPolicy, ...] = ()
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
    effect_types = [type(effect) for effect in spec.effects]
    if len(effect_types) != len(set(effect_types)):
        raise FeaturePolicyConflictError(
            "feature effect policies may be declared only once"
        )
    if any(
        isinstance(effect, ApprovalEffectPolicy)
        for effect in spec.effects
    ) and spec.execution == "readonly":
        raise FeaturePolicyConflictError(
            "readonly feature cannot require confirmation"
        )


def _append_effect[**P, R](
    target: FeatureCallable[P, R],
    effect: FeatureEffectPolicy,
) -> FeatureCallable[P, R]:
    priorities = {
        ApprovalEffectPolicy: 0,
        ObservationEffectPolicy: 1,
        AuditEffectPolicy: 2,
    }
    effects = (*feature_spec(target).effects, effect)
    return _attach(target, effects=tuple(sorted(
        effects,
        key=lambda declared: priorities[type(declared)],
    )))


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


def requires_confirmation[**P, R](
    *,
    action: str,
    resource: str,
    risk: ApprovalRisk = "reversible",
    summary: SummaryBuilder | None = None,
) -> Callable[[FeatureCallable[P, R]], FeatureCallable[P, R]]:
    """Declare confirmation without selecting a frontend."""

    policy = ApprovalEffectPolicy(
        action=action,
        resource=resource,
        risk=risk,
        summary=summary,
    )

    def decorate(target: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
        return _append_effect(target, policy)

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
        return _append_effect(target, ObservationEffectPolicy())

    return decorate(function) if function is not None else decorate


def compact[**P, R](function: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
    """Declare operation/status-only presentation for observed outcomes."""

    return _attach(function, compact=CompactPolicy())


def audited[**P, R](
    event: str,
) -> Callable[[FeatureCallable[P, R]], FeatureCallable[P, R]]:
    """Declare one stable audit identity."""

    policy = AuditEffectPolicy(event)

    def decorate(target: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
        return _append_effect(target, policy)

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
    if any(
        isinstance(effect, ApprovalEffectPolicy)
        for effect in spec.effects
    ) and spec.execution != "mutating":
        raise FeaturePolicyConflictError(
            "confirmation requires a mutating feature"
        )
    return spec
