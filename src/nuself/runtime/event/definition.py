"""Registered contracts for runtime event names and producers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from nuself.runtime.definitions import (
    DefinitionRegistry,
    DefinitionRegistrySealedError,
    DefinitionRegistryUnsealedError,
    DuplicateDefinitionError,
    UnknownDefinitionError,
)
from nuself.runtime.event.payload import (
    validate_runtime_log_event_payload,
)
from nuself.runtime.identities import (
    require_identity_segment,
    require_runtime_event_name,
)

type EventPayloadValidator = Callable[[Mapping[str, object]], None]


class DuplicateEventDefinitionError(ValueError):
    """Raised when a producer/name pair is registered twice."""


class EventDefinitionRegistrySealedError(RuntimeError):
    """Raised when a sealed definition registry is mutated."""


class EventDefinitionRegistryUnsealedError(RuntimeError):
    """Raised when event runtime use starts before composition is sealed."""


class UnknownEventDefinitionError(LookupError):
    """Raised when publication uses an unregistered event."""


@dataclass(frozen=True)
class RuntimeEventDefinition:
    """Stable semantic ownership for one runtime event."""

    producer: str
    name: str
    description: str
    payload_validator: EventPayloadValidator | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        require_identity_segment(
            self.producer,
            label="runtime event producer",
        )
        require_runtime_event_name(self.name)
        if not self.description:
            raise ValueError("event definition description must not be empty")
        if (
            self.payload_validator is not None
            and not callable(self.payload_validator)
        ):
            raise TypeError("event payload validator must be callable")

    def validate_payload(self, payload: Mapping[str, object]) -> None:
        if self.payload_validator is not None:
            self.payload_validator(payload)


class EventDefinitionRegistry:
    """Duplicate-safe event definition registry sealed after composition."""

    def __init__(self) -> None:
        self._registry = DefinitionRegistry[
            tuple[str, str],
            RuntimeEventDefinition,
        ](
            lambda definition: (
                definition.producer,
                definition.name,
            ),
            namespace="runtime event",
        )

    def register(
        self,
        definition: RuntimeEventDefinition,
    ) -> EventDefinitionRegistry:
        try:
            self._registry.register(definition)
        except DefinitionRegistrySealedError as exc:
            raise EventDefinitionRegistrySealedError(
                "event definition registry is sealed"
            ) from exc
        except DuplicateDefinitionError as exc:
            raise DuplicateEventDefinitionError(
                f"event definition already registered: {exc.key!r}"
            ) from exc
        return self

    def resolve(self, producer: str, name: str) -> RuntimeEventDefinition:
        try:
            return self._registry.resolve((producer, name))
        except DefinitionRegistryUnsealedError as exc:
            raise EventDefinitionRegistryUnsealedError(
                "event definition registry must be sealed before runtime use"
            ) from exc
        except UnknownDefinitionError as exc:
            raise UnknownEventDefinitionError(
                f"runtime event is not registered: {(producer, name)!r}"
            ) from exc

    def seal(self) -> EventDefinitionRegistry:
        self._registry.seal()
        return self

    def require_sealed(self) -> None:
        if not self._registry.is_sealed:
            raise EventDefinitionRegistryUnsealedError(
                "event definition registry must be sealed before runtime use"
            )

    @property
    def definitions(self) -> tuple[RuntimeEventDefinition, ...]:
        return self._registry.definitions


CORE_EVENT_DEFINITIONS: tuple[RuntimeEventDefinition, ...] = (
    RuntimeEventDefinition(
        producer="chat",
        name="feature.started",
        description="A declared observed feature started.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="chat",
        name="feature.completed",
        description="A declared observed feature completed.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="chat",
        name="feature.failed",
        description="A declared observed feature failed.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="daemon",
        name="worker.started",
        description="A daemon worker entered its run loop.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="daemon",
        name="worker.stopped",
        description="A daemon worker exited its run loop.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="daemon",
        name="worker.failed",
        description="A daemon worker iteration failed.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="daemon",
        name="task.started",
        description="A unified daemon scheduler task started.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="daemon",
        name="task.completed",
        description="A unified daemon scheduler task completed.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="daemon",
        name="task.failed",
        description="A unified daemon scheduler task failed.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="daemon",
        name="task.deferred",
        description="A durable follow-up wake-up was deferred.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="chat",
        name="turn.started",
        description="A logical chat turn started.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="chat",
        name="turn.completed",
        description="A logical chat turn completed.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="chat",
        name="turn.failed",
        description="A logical chat turn failed.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="chat",
        name="turn.reused",
        description="A completed logical chat turn was returned idempotently.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="chat",
        name="tool.activity",
        description="An agent tool emitted live activity.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="reasoning",
        name="feature.started",
        description="A declared Reason Tool feature started.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="reasoning",
        name="feature.completed",
        description="A declared Reason Tool feature completed.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="reasoning",
        name="feature.failed",
        description="A declared Reason Tool feature failed.",
        payload_validator=validate_runtime_log_event_payload,
    ),
    RuntimeEventDefinition(
        producer="reasoning",
        name="tool.activity",
        description="A Reason Tool emitted live activity.",
        payload_validator=validate_runtime_log_event_payload,
    ),
)


def build_event_definition_registry(
    extensions: Iterable[RuntimeEventDefinition] = (),
) -> EventDefinitionRegistry:
    """Compose core and domain definitions into one sealed registry."""

    registry = EventDefinitionRegistry()
    for definition in (*CORE_EVENT_DEFINITIONS, *extensions):
        registry.register(definition)
    return registry.seal()
