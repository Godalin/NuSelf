"""Orthogonal declarations for application feature functions."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Literal, overload

type Effect = Literal["readonly", "mutating"]
type Risk = Literal["reversible", "destructive", "external"]
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
class ConfirmationPolicy:
    """Declarative confirmation requirement."""

    action: str
    resource: str
    risk: Risk = "reversible"
    summary: SummaryBuilder | None = None

    def __post_init__(self) -> None:
        if not self.action.strip():
            raise ValueError("confirmation action must not be blank")
        if not self.resource.strip():
            raise ValueError("confirmation resource must not be blank")


@dataclass(frozen=True)
class ObservationPolicy:
    """Marker for privacy-safe outcome observation."""


@dataclass(frozen=True)
class CompactPolicy:
    """Marker for intentionally compact observation presentation."""


@dataclass(frozen=True)
class AuditPolicy:
    """Stable domain audit identity."""

    event: str

    def __post_init__(self) -> None:
        if not self.event.strip():
            raise ValueError("audit event must not be blank")


@dataclass(frozen=True)
class FeatureSpec:
    """Immutable policy set attached to a normal Python callable."""

    tool: ToolPolicy | None = None
    component: str | None = None
    effect: Effect | None = None
    confirmation: ConfirmationPolicy | None = None
    observation: ObservationPolicy | None = None
    compact: CompactPolicy | None = None
    audit: AuditPolicy | None = None


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
    if spec.confirmation is not None and spec.effect == "readonly":
        raise FeaturePolicyConflictError(
            "readonly feature cannot require confirmation"
        )


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
    if current.effect == "mutating":
        raise FeaturePolicyConflictError(
            "feature cannot be both readonly and mutating"
        )
    return _attach(function, effect="readonly")


def mutating[**P, R](
    function: FeatureCallable[P, R],
) -> FeatureCallable[P, R]:
    """Declare a state-changing feature."""

    current = feature_spec(function)
    if current.effect == "readonly":
        raise FeaturePolicyConflictError(
            "feature cannot be both readonly and mutating"
        )
    return _attach(function, effect="mutating")


def requires_confirmation[**P, R](
    *,
    action: str,
    resource: str,
    risk: Risk = "reversible",
    summary: SummaryBuilder | None = None,
) -> Callable[[FeatureCallable[P, R]], FeatureCallable[P, R]]:
    """Declare confirmation without selecting a frontend."""

    policy = ConfirmationPolicy(
        action=action,
        resource=resource,
        risk=risk,
        summary=summary,
    )

    def decorate(target: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
        return _attach(target, confirmation=policy)

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
        return _attach(
            target,
            observation=ObservationPolicy(),
        )

    return decorate(function) if function is not None else decorate


def compact[**P, R](function: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
    """Declare operation/status-only presentation for observed outcomes."""

    return _attach(function, compact=CompactPolicy())


def audited[**P, R](
    event: str,
) -> Callable[[FeatureCallable[P, R]], FeatureCallable[P, R]]:
    """Declare one stable audit identity."""

    policy = AuditPolicy(event)

    def decorate(target: FeatureCallable[P, R]) -> FeatureCallable[P, R]:
        return _attach(target, audit=policy)

    return decorate


def require_tool_spec(function: Callable[..., object]) -> FeatureSpec:
    """Return a complete tool spec or fail at composition."""

    spec = feature_spec(function)
    if spec.tool is None:
        raise ValueError("feature function is not declared as a tool")
    if spec.component is None:
        raise ValueError("tool feature requires a component")
    if spec.effect is None:
        raise ValueError("tool feature requires an effect declaration")
    if spec.confirmation is not None and spec.effect != "mutating":
        raise FeaturePolicyConflictError(
            "confirmation requires a mutating feature"
        )
    return spec
