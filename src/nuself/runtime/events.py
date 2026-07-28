"""Synchronous in-process publication for immutable runtime events."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from threading import RLock
from uuid import UUID, uuid4

from nuself.runtime.event_definitions import (
    EventDefinitionRegistry,
    build_event_definition_registry,
)
from nuself.runtime.messages import RuntimeEnvelope

EventSubscriber = Callable[[RuntimeEnvelope], None]


@dataclass(frozen=True)
class EventSubscription:
    """Opaque subscription handle owned by one publisher."""

    publisher_id: UUID
    subscription_id: int


@dataclass(frozen=True)
class EventDeliveryFailure:
    """One subscriber failure captured after independent delivery."""

    subscription: EventSubscription
    error: Exception


class EventDeliveryError(RuntimeError):
    """Raised after all matching subscribers received an event."""

    def __init__(
        self,
        event: RuntimeEnvelope,
        failures: tuple[EventDeliveryFailure, ...],
    ) -> None:
        details = "; ".join(
            (
                f"{type(failure.error).__name__}: "
                f"{str(failure.error).strip() or '<no message>'}"
            )
            for failure in failures
        )
        super().__init__(
            f"{len(failures)} subscriber(s) failed for runtime event "
            f"{event.name!r}: {details}"
        )
        self.event = event
        self.failures = failures


class EventPublisher:
    """Owns ordered subscribers and delivers events synchronously."""

    def __init__(
        self,
        definitions: EventDefinitionRegistry | None = None,
    ) -> None:
        self._lock = RLock()
        self._definitions = (
            definitions
            if definitions is not None
            else build_event_definition_registry()
        )
        self._publisher_id = uuid4()
        self._next_subscription_id = 1
        self._subscribers: dict[int, tuple[str | None, EventSubscriber]] = {}

    def subscribe(
        self,
        subscriber: EventSubscriber,
        *,
        name: str | None = None,
    ) -> EventSubscription:
        """Subscribe to one event name, or all events when name is None."""

        if name == "":
            raise ValueError("event subscription name must not be empty")
        if not callable(subscriber):
            raise TypeError("event subscriber must be callable")
        with self._lock:
            subscription_id = self._next_subscription_id
            self._next_subscription_id += 1
            self._subscribers[subscription_id] = (name, subscriber)
        return EventSubscription(self._publisher_id, subscription_id)

    def unsubscribe(self, subscription: EventSubscription) -> bool:
        """Remove a subscription, returning whether it belonged to this publisher."""

        if subscription.publisher_id != self._publisher_id:
            return False
        with self._lock:
            return self._subscribers.pop(subscription.subscription_id, None) is not None

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
        """Deliver an existing event to every matching subscriber in order."""

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
            subscribers = tuple(self._subscribers.items())
        failures: list[EventDeliveryFailure] = []
        for subscription_id, (name, subscriber) in subscribers:
            if name is not None and name != event.name:
                continue
            try:
                subscriber(event)
            except Exception as exc:  # noqa: BLE001 - isolate independent subscribers
                failures.append(
                    EventDeliveryFailure(
                        EventSubscription(self._publisher_id, subscription_id),
                        exc,
                    )
                )
        if failures:
            raise EventDeliveryError(event, tuple(failures))
