from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest

from nuself.daemon.payloads import (
    ActivityEventsResponsePayload,
    ActivityNextRequestPayload,
    ActivityOpenRequestPayload,
    ActivitySubscriptionPayload,
    ChatRequestPayload,
    ChatResponsePayload,
    DaemonIdentityPayload,
    EmptyPayload,
    SchedulerHealthPayload,
)
from nuself.daemon.protocol import JsonValue, ProtocolError
from nuself.runtime.log_event import LogEvent


def test_chat_request_payload_validates_and_defaults() -> None:
    payload = ChatRequestPayload.from_wire(
        {
            "message": "hello",
        }
    )

    assert payload == ChatRequestPayload(message="hello")


def test_chat_request_payload_requires_message() -> None:
    with pytest.raises(ProtocolError, match="must be a string"):
        ChatRequestPayload.from_wire({"message": 42})


@pytest.mark.parametrize(
    "payload, field",
    [
        (
            {"message": "hello", "conversation_id": 42},
            "conversation_id",
        ),
        (
            {"message": "hello", "turn_id": False},
            "turn_id",
        ),
        (
            {"message": "hello", "mesage": "typo"},
            "mesage",
        ),
    ],
)
def test_chat_request_rejects_invalid_optional_or_unknown_fields(
    payload: dict[str, JsonValue],
    field: str,
) -> None:
    with pytest.raises(ProtocolError, match=field):
        ChatRequestPayload.from_wire(payload)


def test_empty_payload_round_trips_and_rejects_fields() -> None:
    payload = EmptyPayload()

    assert payload.to_wire() == {}
    assert EmptyPayload.from_wire({}) == payload
    with pytest.raises(ProtocolError, match="unexpected"):
        EmptyPayload.from_wire({"unexpected": True})


def test_daemon_identity_payload_contains_only_authority() -> None:
    payload = DaemonIdentityPayload("authority-1")

    assert payload.to_wire() == {"authority_id": "authority-1"}
    assert DaemonIdentityPayload.from_wire(payload.to_wire()) == payload
    with pytest.raises(ProtocolError, match="message"):
        DaemonIdentityPayload.from_wire(
            {"authority_id": "authority-1", "message": "pong"}
        )


def test_chat_response_payload_omits_absent_optional_fields() -> None:
    payload = ChatResponsePayload(
        answer="answer",
        conversation_id="default",
        evidence_references=("m1",),
        epistemic_status="grounded",
    )

    assert payload.to_wire() == {
        "answer": "answer",
        "conversation_id": "default",
        "evidence_references": ["m1"],
        "epistemic_status": "grounded",
    }
    assert ChatResponsePayload.from_wire(payload.to_wire()) == payload


def test_scheduler_health_payload_round_trips_directly() -> None:
    scheduler = SchedulerHealthPayload(
        running=True,
        accepting=True,
        pending=2,
        in_flight=1,
        capacity=4,
        last_error=None,
    )

    assert scheduler.to_wire() == {
        "running": True,
        "accepting": True,
        "pending": 2,
        "in_flight": 1,
        "capacity": 4,
        "last_error": None,
    }
    assert SchedulerHealthPayload.from_wire(scheduler.to_wire()) == scheduler


@pytest.mark.parametrize(
    "payload, error",
    [
        (
            {
                "running": "yes",
                "accepting": True,
                "pending": 0,
                "in_flight": 0,
                "capacity": 4,
                "last_error": None,
            },
            "running",
        ),
        (
            {
                "answer": "answer",
                "conversation_id": "default",
                "evidence_references": [1],
                "epistemic_status": "grounded",
            },
            "evidence_references",
        ),
        (
            {
                "answer": "answer",
                "conversation_id": "default",
                "evidence_references": [],
                "epistemic_status": "invented",
            },
            "epistemic_status",
        ),
        (
            {
                "answer": "answer",
                "conversation_id": "default",
                "evidence_references": [],
                "epistemic_status": None,
                "confidence": 2,
            },
            "confidence",
        ),
    ],
)
def test_response_payloads_reject_malformed_nested_fields(
    payload: dict[str, JsonValue],
    error: str,
) -> None:
    decoder = (
        SchedulerHealthPayload.from_wire
        if "running" in payload
        else ChatResponsePayload.from_wire
    )
    with pytest.raises(ProtocolError, match=error):
        decoder(payload)


def test_activity_response_payloads_round_trip_and_fail_atomically() -> None:
    event = LogEvent(
        time="2026-07-28T00:00:00+00:00",
        level="info",
        component="daemon",
        event="test",
        message="test event",
    )
    opened = ActivitySubscriptionPayload("sub-1")
    events = ActivityEventsResponsePayload((event,))

    assert ActivitySubscriptionPayload.from_wire(
        opened.to_wire()
    ) == opened
    assert ActivityEventsResponsePayload.from_wire(
        events.to_wire()
    ) == events
    malformed = events.to_wire()
    raw_events = malformed["events"]
    assert isinstance(raw_events, list)
    raw_events.append({"component": "invalid"})
    with pytest.raises(ProtocolError, match=r"event\[1\]"):
        ActivityEventsResponsePayload.from_wire(malformed)

    for dropped_count in (-1, True, "1"):
        malformed_count = events.to_wire()
        malformed_count["dropped_count"] = cast(
            JsonValue,
            dropped_count,
        )
        with pytest.raises(ProtocolError, match="dropped_count"):
            ActivityEventsResponsePayload.from_wire(malformed_count)


def test_activity_payloads_validate_bounds() -> None:
    assert (
        ActivityOpenRequestPayload.from_wire({"turn_id": "turn-1"}).turn_id == "turn-1"
    )
    assert ActivityNextRequestPayload.from_wire(
        {
            "subscription_id": "sub-1",
            "timeout_ms": 100,
            "limit": 25,
        }
    ) == ActivityNextRequestPayload(
        subscription_id="sub-1",
        timeout_ms=100,
        limit=25,
    )

    with pytest.raises(ProtocolError, match="timeout_ms"):
        ActivityNextRequestPayload.from_wire(
            {
                "subscription_id": "sub-1",
                "timeout_ms": 5_001,
            }
        )


@pytest.mark.parametrize(
    "decode, payload, field",
    [
        (
            ActivityOpenRequestPayload.from_wire,
            {"turn_id": "turn-1", "extra": True},
            "extra",
        ),
        (
            ActivityNextRequestPayload.from_wire,
            {
                "subscription_id": "sub-1",
                "timeout_ms": False,
            },
            "timeout_ms",
        ),
        (
            ActivityNextRequestPayload.from_wire,
            {
                "subscription_id": "sub-1",
                "limit": 10,
                "limt": 10,
            },
            "limt",
        ),
        (
            ActivitySubscriptionPayload.from_wire,
            {"subscription_id": "   "},
            "non-blank",
        ),
    ],
)
def test_activity_payloads_reject_invalid_or_unknown_fields(
    decode: Callable[[dict[str, JsonValue]], object],
    payload: dict[str, JsonValue],
    field: str,
) -> None:
    with pytest.raises(ProtocolError, match=field):
        decode(payload)
