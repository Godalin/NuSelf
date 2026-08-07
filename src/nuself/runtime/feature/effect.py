"""Declaration and invocation abstractions for composable Tool effects."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass
import time
from typing import ClassVar, Literal, Protocol

from langchain_core.tools import ToolException

from nuself.runtime.feature.protocol import ToolEffectPort

type Execution = Literal["readonly", "mutating"]


class FeatureEventPublisher(Protocol):
    """Runtime event capability consumed by projection effects."""

    def publish(
        self,
        *,
        name: str,
        producer: str,
        payload: Mapping[str, object] | None = None,
    ) -> object: ...


@dataclass(frozen=True)
class FeatureAuditRecord:
    """Payload-safe outcome for a declared domain audit."""

    component: str
    event: str
    operation: str
    outcome: str
    error_type: str | None = None


class FeatureAuditProjection(Protocol):
    """Non-raising durable audit projection adapter boundary."""

    def project_best_effort(self, record: FeatureAuditRecord) -> None:
        """Project a record and observably contain persistence failures."""
        ...


class FeatureEffectRejected(ToolException):
    """A suspending effect was resolved without permission to execute."""


@dataclass(frozen=True)
class EffectEnvironment:
    """Explicit runtime capabilities available while binding effects."""

    producer: str
    effect_port: ToolEffectPort
    events: FeatureEventPublisher | None = None
    audits: FeatureAuditProjection | None = None

    def __post_init__(self) -> None:
        if not self.producer.strip():
            raise ValueError("Tool effect producer must not be blank")


@dataclass(frozen=True)
class FeatureInvocation:
    """One immutable feature call shared with bound effects."""

    component: str
    operation: str
    execution: Execution | None
    args: tuple[object, ...]
    kwargs: Mapping[str, object]
    started_at: float

    @classmethod
    def from_call(
        cls,
        function: Callable[..., object],
        *,
        component: str | None,
        operation: str | None,
        execution: Execution | None,
        args: tuple[object, ...],
        kwargs: Mapping[str, object],
    ) -> FeatureInvocation:
        return cls(
            component=component or "runtime",
            operation=operation or function.__name__,
            execution=execution,
            args=args,
            kwargs=dict(kwargs),
            started_at=time.monotonic(),
        )

    @property
    def duration_ms(self) -> int:
        return max(0, int((time.monotonic() - self.started_at) * 1000))


class FeatureEffect(ABC):
    """Immutable declaration attached to a feature function."""

    cardinality_key: ClassVar[str | None] = None

    @abstractmethod
    def bind(self, environment: EffectEnvironment) -> BoundFeatureEffect:
        """Bind this declaration to fresh invocation runtime state."""


class ExecutionConstraint(ABC):
    """Optional declaration capability for execution compatibility."""

    @abstractmethod
    def validate_execution(self, execution: Execution | None) -> None:
        """Reject an incompatible execution classification."""


class BoundFeatureEffect(ABC):
    """Invocation-scoped runtime implementation of one effect."""

    before_priority: ClassVar[int] = 100
    after_priority: ClassVar[int] = 100
    failure_priority: ClassVar[int] = 100

    def before(self, invocation: FeatureInvocation) -> None:
        del invocation

    def after(self, invocation: FeatureInvocation, result: object) -> None:
        del invocation, result

    def failed(self, invocation: FeatureInvocation, error: Exception) -> None:
        del invocation, error
