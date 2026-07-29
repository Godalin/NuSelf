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


def test_event_publisher_delivers_matching_projections_in_order() -> None:
    publisher = EventPublisher()
    received: list[str] = []
    publisher.attach_projection(lambda event: received.append(f"all:{event.name}"))
    publisher.attach_projection(
        lambda event: received.append(f"named:{event.name}"),
        producer="daemon",
        name="worker.started",
    )
    publisher.attach_projection(
        lambda event: received.append(f"other:{event.name}"),
        producer="daemon",
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
        raise RuntimeError("projection failed")

    failed_projection = publisher.attach_projection(fail)
    publisher.attach_projection(lambda event: received.append(event.name))

    with pytest.raises(EventDeliveryError) as exc_info:
        publisher.publish(name="worker.started", producer="daemon")

    assert received == ["worker.started"]
    assert len(exc_info.value.failures) == 1
    assert exc_info.value.failures[0].projection == failed_projection
    assert str(exc_info.value.failures[0].error) == "projection failed"


def test_event_delivery_retains_exception_with_broken_string_renderer() -> None:
    publisher = EventPublisher()

    class BrokenMessageError(RuntimeError):
        def __str__(self) -> str:
            raise RuntimeError("message rendering failed")

    projection_error = BrokenMessageError()

    def fail(_event: RuntimeEnvelope) -> None:
        raise projection_error

    failed_projection = publisher.attach_projection(fail)

    with pytest.raises(EventDeliveryError) as exc_info:
        publisher.publish(name="worker.started", producer="daemon")

    [failure] = exc_info.value.failures
    assert failure.projection == failed_projection
    assert failure.error is projection_error
    assert "BrokenMessageError: <no message>" in str(exc_info.value)


def test_event_projection_can_be_removed() -> None:
    publisher = EventPublisher()
    received: list[str] = []
    projection = publisher.attach_projection(lambda event: received.append(event.name))

    assert publisher.detach_projection(projection) is True
    assert publisher.detach_projection(projection) is False
    publisher.publish(name="worker.started", producer="daemon")

    assert received == []


def test_event_publisher_rejects_non_callable_projection() -> None:
    publisher = EventPublisher()

    with pytest.raises(TypeError, match="event projection must be callable"):
        publisher.attach_projection(None)  # type: ignore[arg-type]

    publisher.publish(name="worker.started", producer="daemon")


@pytest.mark.parametrize(
    ("producer", "name"),
    (
        ("daemon", None),
        (None, "worker.started"),
    ),
)
def test_event_publisher_rejects_partial_projection_identity(
    producer: str | None,
    name: str | None,
) -> None:
    publisher = EventPublisher()

    with pytest.raises(
        ValueError,
        match="producer and name must be supplied together",
    ):
        publisher.attach_projection(
            lambda _event: None,
            producer=producer,
            name=name,
        )


def test_event_publisher_rejects_unknown_exact_projection() -> None:
    publisher = EventPublisher()

    with pytest.raises(UnknownEventDefinitionError):
        publisher.attach_projection(
            lambda _event: None,
            producer="chat",
            name="worker.started",
        )


def test_exact_projection_isolates_same_name_across_producers() -> None:
    definitions = build_event_definition_registry(
        (
            RuntimeEventDefinition(
                producer="chat",
                name="worker.started",
                description="Extension event with a colliding name.",
            ),
        )
    )
    publisher = EventPublisher(definitions)
    received: list[tuple[str, str]] = []
    publisher.attach_projection(
        lambda event: received.append((event.producer, event.name)),
        producer="daemon",
        name="worker.started",
    )

    publisher.publish(name="worker.started", producer="chat")
    publisher.publish(name="worker.started", producer="daemon")

    assert received == [("daemon", "worker.started")]


def test_event_projection_is_bound_to_one_publisher_lifetime() -> None:
    earlier_publisher = EventPublisher()
    current_publisher = EventPublisher()
    earlier_projection = earlier_publisher.attach_projection(lambda _event: None)
    received: list[str] = []
    current_projection = current_publisher.attach_projection(
        lambda event: received.append(event.name)
    )

    assert earlier_projection.projection_id == current_projection.projection_id
    assert earlier_projection.publisher_id != current_projection.publisher_id
    assert current_publisher.detach_projection(earlier_projection) is False

    current_publisher.publish(name="worker.started", producer="daemon")

    assert received == ["worker.started"]
    assert current_publisher.detach_projection(current_projection) is True


def test_projection_mutations_do_not_change_active_delivery_snapshot() -> None:
    publisher = EventPublisher()
    received: list[str] = []

    def mutate_projections(event: RuntimeEnvelope) -> None:
        received.append(f"mutator:{event.name}")
        if event.name != "worker.started":
            return
        assert publisher.detach_projection(removed_projection) is True
        publisher.attach_projection(
            lambda later_event: received.append(f"added:{later_event.name}")
        )

    publisher.attach_projection(mutate_projections)
    removed_projection = publisher.attach_projection(
        lambda event: received.append(f"removed:{event.name}")
    )

    publisher.publish(name="worker.started", producer="daemon")

    assert received == [
        "mutator:worker.started",
        "removed:worker.started",
    ]

    publisher.publish(name="worker.stopped", producer="daemon")

    assert received == [
        "mutator:worker.started",
        "removed:worker.started",
        "mutator:worker.stopped",
        "added:worker.stopped",
    ]


def test_projection_mutations_are_visible_to_nested_publication() -> None:
    publisher = EventPublisher()
    received: list[str] = []

    def publish_nested(event: RuntimeEnvelope) -> None:
        received.append(f"publisher:{event.name}")
        if event.name != "worker.started":
            return
        assert publisher.detach_projection(removed_projection) is True
        publisher.attach_projection(
            lambda nested_event: received.append(f"added:{nested_event.name}")
        )
        publisher.publish(name="worker.stopped", producer="daemon")

    publisher.attach_projection(publish_nested)
    removed_projection = publisher.attach_projection(
        lambda event: received.append(f"removed:{event.name}")
    )

    publisher.publish(name="worker.started", producer="daemon")

    assert received == [
        "publisher:worker.started",
        "publisher:worker.stopped",
        "added:worker.stopped",
        "removed:worker.started",
    ]


def test_runtime_event_log_sink_preserves_event_identity(tmp_path: Path) -> None:
    publisher = EventPublisher()
    publisher.attach_projection(runtime_event_log_sink(tmp_path))

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


def test_runtime_event_log_sink_sanitizes_without_mutating_envelope(
    tmp_path: Path,
) -> None:
    publisher = EventPublisher()
    publisher.attach_projection(runtime_event_log_sink(tmp_path))
    payload = {
        "message": "worker started api_key=message-secret",
        "status": "started",
        "error": "provider rejected token=error-secret",
        "metadata": {
            "worker": "memory",
            "clientSecret": "metadata-secret",
            "detail": "request used access_token=query-secret",
        },
    }

    event = publisher.publish(
        name="worker.started",
        producer="daemon",
        payload=payload,
    )

    [logged] = read_log_events(project_root=tmp_path, component="daemon")
    assert logged.message == "worker started api_key=***"
    assert logged.error == "provider rejected token=***"
    assert logged.metadata == {
        "worker": "memory",
        "clientSecret": "***",
        "detail": "request used access_token=***",
    }
    assert event.payload == payload


def test_event_publisher_rejects_unknown_or_wrong_producer() -> None:
    publisher = EventPublisher()

    with pytest.raises(UnknownEventDefinitionError):
        publisher.publish(name="worker.started", producer="chat")
    with pytest.raises(UnknownEventDefinitionError):
        publisher.publish(name="domain.changed", producer="memory")


def test_core_event_payload_is_validated_before_projection_delivery() -> None:
    publisher = EventPublisher()
    received: list[RuntimeEnvelope] = []
    publisher.attach_projection(received.append)

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
    publisher.attach_projection(received.append)
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
    publisher.attach_projection(lambda event: received.append(event.payload))
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


def test_event_definition_rejects_non_callable_payload_validator() -> None:
    with pytest.raises(
        TypeError,
        match="event payload validator must be callable",
    ):
        RuntimeEventDefinition(
            producer="memory",
            name="entry.changed",
            description="A durable memory entry changed.",
            payload_validator=object(),  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "producer",
    ("", "Memory", "memory-agent", "1memory", "memory.agent"),
)
def test_event_definition_rejects_invalid_producer_identity(
    producer: str,
) -> None:
    with pytest.raises(ValueError, match="runtime event producer"):
        RuntimeEventDefinition(
            producer=producer,
            name="entry.changed",
            description="A durable memory entry changed.",
        )


@pytest.mark.parametrize(
    "name",
    (
        "",
        "changed",
        "Entry.changed",
        "entry-changed",
        "entry..changed",
        "1entry.changed",
        "entry.1changed",
    ),
)
def test_event_definition_rejects_invalid_runtime_event_name(
    name: str,
) -> None:
    with pytest.raises(ValueError, match="runtime event name"):
        RuntimeEventDefinition(
            producer="memory",
            name=name,
            description="A durable memory entry changed.",
        )


def test_event_definition_accepts_multi_segment_runtime_event_name() -> None:
    definition = RuntimeEventDefinition(
        producer="reason",
        name="reason.output.export",
        description="A reason output export changed state.",
    )

    assert definition.name == "reason.output.export"
