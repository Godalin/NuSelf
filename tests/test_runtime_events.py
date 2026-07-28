from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from nuself.logs import (
    read_log_events,
    runtime_event_log_sink,
    write_runtime_event,
)
from nuself.runtime import (
    DuplicateEventDefinitionError,
    EventDefinitionRegistry,
    EventDefinitionRegistrySealedError,
    EventDeliveryError,
    EventPublisher,
    RuntimeLogEventPayload,
    RuntimeEnvelope,
    RuntimeEventDefinition,
    UnknownEventDefinitionError,
    build_event_definition_registry,
)


def test_event_publisher_delivers_matching_subscribers_in_order() -> None:
    publisher = EventPublisher()
    received: list[str] = []
    publisher.subscribe(lambda event: received.append(f"all:{event.name}"))
    publisher.subscribe(
        lambda event: received.append(f"named:{event.name}"),
        name="worker.started",
    )
    publisher.subscribe(
        lambda event: received.append(f"other:{event.name}"),
        name="worker.stopped",
    )

    event = publisher.publish(
        name="worker.started",
        producer="daemon",
        payload={"metadata": {"worker": "memory"}},
    )

    assert received == ["all:worker.started", "named:worker.started"]
    assert event.payload == {"metadata": {"worker": "memory"}}


def test_event_publisher_delivers_independently_then_reports_failures() -> None:
    publisher = EventPublisher()
    received: list[str] = []

    def fail(_event: RuntimeEnvelope) -> None:
        raise RuntimeError("subscriber failed")

    failed_subscription = publisher.subscribe(fail)
    publisher.subscribe(lambda event: received.append(event.name))

    with pytest.raises(EventDeliveryError) as exc_info:
        publisher.publish(name="worker.started", producer="daemon")

    assert received == ["worker.started"]
    assert len(exc_info.value.failures) == 1
    assert exc_info.value.failures[0].subscription == failed_subscription
    assert str(exc_info.value.failures[0].error) == "subscriber failed"


def test_event_subscription_can_be_removed() -> None:
    publisher = EventPublisher()
    received: list[str] = []
    subscription = publisher.subscribe(lambda event: received.append(event.name))

    assert publisher.unsubscribe(subscription) is True
    assert publisher.unsubscribe(subscription) is False
    publisher.publish(name="worker.started", producer="daemon")

    assert received == []


def test_event_subscription_is_bound_to_one_publisher_lifetime() -> None:
    earlier_publisher = EventPublisher()
    current_publisher = EventPublisher()
    earlier_subscription = earlier_publisher.subscribe(lambda _event: None)
    received: list[str] = []
    current_subscription = current_publisher.subscribe(
        lambda event: received.append(event.name)
    )

    assert earlier_subscription.subscription_id == current_subscription.subscription_id
    assert earlier_subscription.publisher_id != current_subscription.publisher_id
    assert current_publisher.unsubscribe(earlier_subscription) is False

    current_publisher.publish(name="worker.started", producer="daemon")

    assert received == ["worker.started"]
    assert current_publisher.unsubscribe(current_subscription) is True


def test_runtime_event_log_sink_preserves_event_identity(tmp_path: Path) -> None:
    publisher = EventPublisher()
    publisher.subscribe(runtime_event_log_sink(tmp_path))

    event = publisher.publish(
        name="worker.started",
        producer="daemon",
        payload={
            "message": "worker started",
            "status": "started",
            "metadata": {"worker": "memory"},
        },
    )

    [logged] = read_log_events(project_root=tmp_path, component="daemon")
    assert logged.event_id == event.message_id
    assert logged.event == event.name
    assert logged.status == "started"
    assert logged.metadata == {"worker": "memory"}


def test_event_publisher_rejects_unknown_or_wrong_producer() -> None:
    publisher = EventPublisher()

    with pytest.raises(UnknownEventDefinitionError):
        publisher.publish(name="worker.started", producer="chat")
    with pytest.raises(UnknownEventDefinitionError):
        publisher.publish(name="domain.changed", producer="memory")


def test_core_event_payload_is_validated_before_subscriber_delivery() -> None:
    publisher = EventPublisher()
    received: list[RuntimeEnvelope] = []
    publisher.subscribe(received.append)

    with pytest.raises(
        ValueError,
        match="unknown fields",
    ):
        publisher.publish(
            name="worker.started",
            producer="daemon",
            payload={"worker": "memory"},
        )

    assert received == []


def test_existing_core_event_envelope_is_validated_before_delivery() -> None:
    publisher = EventPublisher()
    received: list[RuntimeEnvelope] = []
    publisher.subscribe(received.append)
    envelope = RuntimeEnvelope(
        kind="event",
        name="worker.started",
        producer="daemon",
        payload={"worker": "memory"},
    )

    with pytest.raises(ValueError, match="unknown fields"):
        publisher.publish_envelope(envelope)

    assert received == []


@pytest.mark.parametrize(
    ("payload", "error_type", "message"),
    [
        ({"level": "verbose"}, ValueError, "level is invalid"),
        ({"status": 1}, TypeError, "status must be a string"),
        (
            {"duration_ms": True},
            TypeError,
            "duration_ms must be an integer",
        ),
        (
            {"duration_ms": -1},
            TypeError,
            "non-negative integer",
        ),
        ({"metadata": []}, TypeError, "metadata must be a mapping"),
    ],
)
def test_runtime_log_payload_rejects_invalid_projection_fields(
    payload: dict[str, object],
    error_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        RuntimeLogEventPayload.from_mapping(payload)


def test_runtime_log_sink_reuses_strict_payload_parser(
    tmp_path: Path,
) -> None:
    envelope = RuntimeEnvelope(
        kind="event",
        name="worker.started",
        producer="daemon",
        payload={"worker": "memory"},
    )

    with pytest.raises(ValueError, match="unknown fields"):
        write_runtime_event(envelope, project_root=tmp_path)

    assert read_log_events(project_root=tmp_path) == []


def test_domain_event_definitions_extend_core_registry() -> None:
    definition = RuntimeEventDefinition(
        producer="memory",
        name="entry.changed",
        description="A durable memory entry changed.",
    )
    publisher = EventPublisher(build_event_definition_registry((definition,)))

    event = publisher.publish(
        name="entry.changed",
        producer="memory",
        payload={"entry_id": "m1"},
    )

    assert event.name == "entry.changed"


def test_event_publish_validates_canonical_payload_exactly_once() -> None:
    validated: list[Mapping[str, object]] = []
    received: list[Mapping[str, object]] = []
    definition = RuntimeEventDefinition(
        producer="memory",
        name="entry.changed",
        description="A durable memory entry changed.",
        payload_validator=validated.append,
    )
    publisher = EventPublisher(
        build_event_definition_registry((definition,))
    )
    publisher.subscribe(lambda event: received.append(event.payload))
    payload = {"entries": ["m1"]}

    event = publisher.publish(
        name="entry.changed",
        producer="memory",
        payload=payload,
    )

    assert validated == [event.payload]
    assert received == [event.payload]
    assert validated[0] is event.payload
    assert received[0] is event.payload
    assert event.payload["entries"] == ("m1",)


def test_existing_event_envelope_is_validated_exactly_once() -> None:
    validated: list[Mapping[str, object]] = []
    definition = RuntimeEventDefinition(
        producer="memory",
        name="entry.changed",
        description="A durable memory entry changed.",
        payload_validator=validated.append,
    )
    publisher = EventPublisher(
        build_event_definition_registry((definition,))
    )
    event = RuntimeEnvelope(
        kind="event",
        name="entry.changed",
        producer="memory",
        payload={"entry_id": "m1"},
    )

    publisher.publish_envelope(event)

    assert validated == [event.payload]
    assert validated[0] is event.payload


def test_event_definition_registry_rejects_duplicates_and_late_changes() -> None:
    definition = RuntimeEventDefinition(
        producer="memory",
        name="entry.changed",
        description="A durable memory entry changed.",
    )
    registry = EventDefinitionRegistry().register(definition)

    with pytest.raises(DuplicateEventDefinitionError):
        registry.register(definition)

    registry.seal()
    with pytest.raises(EventDefinitionRegistrySealedError):
        registry.register(
            RuntimeEventDefinition(
                producer="memory",
                name="entry.deleted",
                description="A durable memory entry was deleted.",
            )
        )
