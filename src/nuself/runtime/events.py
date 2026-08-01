"""Synchronous in-process publication for immutable runtime events."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import Lock
from uuid import UUID, uuid4

from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.runtime.event_definitions import (
    EventDefinitionRegistry,
    build_event_definition_registry,
)
from nuself.runtime.messages import RuntimeEnvelope

EventProjection = Callable[[RuntimeEnvelope], None]


@dataclass(frozen=True)
class EventProjectionHandle:
    """Opaque projection handle owned by one publisher."""

    publisher_id: UUID
    projection_id: int


@dataclass(frozen=True)
class EventDeliveryFailure:
    """One projection failure captured after independent delivery."""

    projection: EventProjectionHandle
    error: Exception


class EventDeliveryError(RuntimeError):
    """Raised after all matching projections received an event."""

    def __init__(
        self,
        event: RuntimeEnvelope,
        failures: tuple[EventDeliveryFailure, ...],
    ) -> None:
        details = "; ".join(
            (
                f"{type(failure.error).__name__}: "
                f"{diagnostic_exception_message(
                    failure.error,
                    empty='<no message>',
                )}"
            )
            for failure in failures
        )
        super().__init__(
            f"{len(failures)} projection(s) failed for runtime event "
            f"{event.name!r}: {details}"
        )
        self.event = event
        self.failures = failures


class EventPublisher:
    """Owns ordered projections and delivers events synchronously."""

    def __init__(
        self,
        definitions: EventDefinitionRegistry | None = None,
    ) -> None:
        self._lock = Lock()
        self._definitions = (
            definitions
            if definitions is not None
            else build_event_definition_registry()
        )
        self._definitions.require_sealed()
        self._publisher_id = uuid4()
        self._next_projection_id = 1
        self._projections: dict[
            int,
            tuple[tuple[str, str] | None, EventProjection],
        ] = {}

    def attach_projection(
        self,
        projection: EventProjection,
        *,
        producer: str | None = None,
        name: str | None = None,
    ) -> EventProjectionHandle:
        """Attach a synchronous projection to one identity, or all events."""

        if not callable(projection):
            raise TypeError("event projection must be callable")
        if (producer is None) != (name is None):
            raise ValueError(
                "event projection producer and name must be supplied together"
            )
        selector: tuple[str, str] | None = None
        if producer is not None and name is not None:
            self._definitions.resolve(producer, name)
            selector = (producer, name)
        with self._lock:
            projection_id = self._next_projection_id
            self._next_projection_id += 1
            self._projections[projection_id] = (selector, projection)
        return EventProjectionHandle(self._publisher_id, projection_id)

    def detach_projection(self, projection: EventProjectionHandle) -> bool:
        """Detach a projection, returning whether it belonged to this publisher."""

        if projection.publisher_id != self._publisher_id:
            return False
        with self._lock:
            return self._projections.pop(projection.projection_id, None) is not None

    def publish(
        self,
        *,
        name: str,
        producer: str,
        payload: Mapping[str, object] | None = None,
    ) -> RuntimeEnvelope:
        """Create and synchronously publish one immutable event."""

        definition = self._definitions.resolve(producer, name)
        event_payload: Mapping[str, object] = (
            {} if payload is None else payload
        )
        event = RuntimeEnvelope(
            kind="event",
            name=name,
            producer=producer,
            payload=event_payload,
        )
        definition.validate_payload(event.payload)
        self._deliver_validated_envelope(event)
        return event

    def publish_envelope(self, event: RuntimeEnvelope) -> None:
        """Deliver an existing event to every matching projection in order."""

        if event.kind != "event":
            raise ValueError("event publisher requires an event envelope")
        definition = self._definitions.resolve(
            event.producer,
            event.name,
        )
        definition.validate_payload(event.payload)
        self._deliver_validated_envelope(event)

    def _deliver_validated_envelope(
        self,
        event: RuntimeEnvelope,
    ) -> None:
        """Deliver one definition-validated immutable event."""

        with self._lock:
            projections = tuple(self._projections.items())
        failures: list[EventDeliveryFailure] = []
        for projection_id, (selector, projection) in projections:
            if selector is not None and selector != (
                event.producer,
                event.name,
            ):
                continue
            try:
                projection(event)
            except Exception as exc:  # noqa: BLE001 - isolate independent projections
                failures.append(
                    EventDeliveryFailure(
                        EventProjectionHandle(self._publisher_id, projection_id),
                        exc,
                    )
                )
        if failures:
            raise EventDeliveryError(event, tuple(failures))
