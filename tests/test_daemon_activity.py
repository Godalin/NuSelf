from __future__ import annotations

from pathlib import Path

import pytest

from nuself.daemon.activity import (
    ActivityBroker,
    ActivitySubscriptionNotFound,
)
from nuself.daemon.protocol import DaemonRequest
from nuself.daemon.request_handlers import handle_request
from nuself.daemon.state import DaemonState
from nuself.logs import LogEvent, observe_log_events, write_log_event


def _event(turn_id: str, message: str) -> LogEvent:
    return LogEvent(
        time="2026-01-01T00:00:00Z",
        level="info",
        component="chat",
        event="tool_activity",
        message=message,
        turn_id=turn_id,
    )


def test_activity_broker_filters_turns_and_bounds_queues() -> None:
    broker = ActivityBroker(max_events_per_subscription=2)
    subscription_id = broker.open("turn-1")

    broker.publish(_event("other", "ignored"))
    broker.publish(_event("turn-1", "first"))
    broker.publish(_event("turn-1", "second"))
    broker.publish(_event("turn-1", "third"))

    events = broker.next_events(
        subscription_id,
        timeout_seconds=0,
        limit=10,
    )
    assert [event.message for event in events] == ["second", "third"]


def test_activity_broker_close_and_expiry() -> None:
    broker = ActivityBroker(subscription_ttl_seconds=0.001)
    subscription_id = broker.open("turn-1")
    assert broker.close(subscription_id) is True
    assert broker.close(subscription_id) is False

    with pytest.raises(ActivitySubscriptionNotFound):
        broker.next_events(
            subscription_id,
            timeout_seconds=0,
            limit=1,
        )


def test_daemon_activity_request_lifecycle(tmp_path: Path) -> None:
    state = DaemonState(tmp_path)
    opened = handle_request(
        DaemonRequest(
            type="activity_open",
            payload={"turn_id": "turn-1"},
            request_id="open",
        ),
        state,
    )
    subscription_id = opened.payload["subscription_id"]
    assert isinstance(subscription_id, str)

    state.activity_broker.publish(_event("turn-1", "live"))
    received = handle_request(
        DaemonRequest(
            type="activity_next",
            payload={
                "subscription_id": subscription_id,
                "timeout_ms": 0,
                "limit": 10,
            },
            request_id="next",
        ),
        state,
    )
    raw_events = received.payload["events"]
    assert isinstance(raw_events, list)
    assert len(raw_events) == 1

    closed = handle_request(
        DaemonRequest(
            type="activity_close",
            payload={"subscription_id": subscription_id},
            request_id="close",
        ),
        state,
    )
    assert closed.payload == {"closed": True}


def test_request_scoped_log_projection_reaches_activity_broker(
    tmp_path: Path,
) -> None:
    broker = ActivityBroker()
    subscription_id = broker.open("turn-1")

    with observe_log_events(broker.publish):
        written = write_log_event(
            "chat",
            "tool_activity",
            "live",
            project_root=tmp_path,
            turn_id="turn-1",
        )

    assert broker.next_events(
        subscription_id,
        timeout_seconds=0,
        limit=10,
    ) == (written,)
