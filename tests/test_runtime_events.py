from __future__ import annotations

from pathlib import Path

import pytest

from nuself.logs import read_log_events, runtime_event_log_sink
from nuself.runtime import EventDeliveryError, EventPublisher, RuntimeEnvelope


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
        payload={"worker": "memory"},
    )

    assert received == ["all:worker.started", "named:worker.started"]
    assert event.payload == {"worker": "memory"}


def test_event_publisher_delivers_independently_then_reports_failures() -> None:
    publisher = EventPublisher()
    received: list[str] = []

    def fail(_event: RuntimeEnvelope) -> None:
        raise RuntimeError("subscriber failed")

    publisher.subscribe(fail)
    publisher.subscribe(lambda event: received.append(event.name))

    with pytest.raises(EventDeliveryError) as exc_info:
        publisher.publish(name="worker.started", producer="daemon")

    assert received == ["worker.started"]
    assert len(exc_info.value.failures) == 1
    assert str(exc_info.value.failures[0].error) == "subscriber failed"


def test_event_subscription_can_be_removed() -> None:
    publisher = EventPublisher()
    received: list[str] = []
    subscription = publisher.subscribe(lambda event: received.append(event.name))

    assert publisher.unsubscribe(subscription) is True
    assert publisher.unsubscribe(subscription) is False
    publisher.publish(name="worker.started", producer="daemon")

    assert received == []


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
