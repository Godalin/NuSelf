"""Registered contracts for runtime event names and producers."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from threading import RLock

from nuself.runtime.event_payloads import (
    validate_runtime_log_event_payload,
)

EventPayloadValidator = Callable[[Mapping[str, object]], None]


class DuplicateEventDefinitionError(ValueError):
    """Raised when a producer/name pair is registered twice."""


class EventDefinitionRegistrySealedError(RuntimeError):
    """Raised when a sealed definition registry is mutated."""


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
        if not self.producer or not self.name or not self.description:
            raise ValueError("event definition fields must not be empty")
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
        self._definitions: dict[tuple[str, str], RuntimeEventDefinition] = {}
        self._sealed = False
        self._lock = RLock()

    def register(
        self,
        definition: RuntimeEventDefinition,
    ) -> EventDefinitionRegistry:
        key = (definition.producer, definition.name)
        with self._lock:
            if self._sealed:
                raise EventDefinitionRegistrySealedError(
                    "event definition registry is sealed"
                )
            if key in self._definitions:
                raise DuplicateEventDefinitionError(
                    f"event definition already registered: {key!r}"
                )
            self._definitions[key] = definition
        return self

    def resolve(self, producer: str, name: str) -> RuntimeEventDefinition:
        with self._lock:
            definition = self._definitions.get((producer, name))
        if definition is None:
            raise UnknownEventDefinitionError(
                f"runtime event is not registered: {(producer, name)!r}"
            )
        return definition

    def seal(self) -> EventDefinitionRegistry:
        with self._lock:
            self._sealed = True
        return self

    @property
    def definitions(self) -> tuple[RuntimeEventDefinition, ...]:
        with self._lock:
            return tuple(self._definitions.values())


CORE_EVENT_DEFINITIONS: tuple[RuntimeEventDefinition, ...] = (
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
)


def build_event_definition_registry(
    extensions: Iterable[RuntimeEventDefinition] = (),
) -> EventDefinitionRegistry:
    """Compose core and domain definitions into one sealed registry."""

    registry = EventDefinitionRegistry()
    for definition in (*CORE_EVENT_DEFINITIONS, *extensions):
        registry.register(definition)
    return registry.seal()
