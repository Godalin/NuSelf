from __future__ import annotations

from collections.abc import Callable
from typing import cast

import pytest

from nuself.daemon.payloads import (
    ActivityCloseRequestPayload,
    ActivityCloseResponsePayload,
    ActivityEventsResponsePayload,
    ActivityNextRequestPayload,
    ActivityOpenRequestPayload,
    ActivityOpenResponsePayload,
    ChatRequestPayload,
    ChatResponsePayload,
    EmptyRequestPayload,
    HealthResponsePayload,
    MessagePayload,
    WorkerHealthPayload,
)
from nuself.daemon.protocol import JsonValue, ProtocolError
from nuself.daemon.types import WorkerHealth
from nuself.logs import LogEvent


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
            {"message": "hello", "thread_id": 42},
            "thread_id",
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


def test_empty_request_payload_rejects_fields() -> None:
    assert EmptyRequestPayload.from_wire({}) == EmptyRequestPayload()
    with pytest.raises(ProtocolError, match="unexpected"):
        EmptyRequestPayload.from_wire({"unexpected": True})


def test_chat_response_payload_omits_absent_optional_fields() -> None:
    payload = ChatResponsePayload(
        answer="answer",
        reply="answer",
        thread_id="default",
        evidence_references=("m1",),
        epistemic_status="grounded",
    )

    assert payload.to_wire() == {
        "answer": "answer",
        "reply": "answer",
        "thread_id": "default",
        "evidence_references": ["m1"],
        "epistemic_status": "grounded",
    }
    assert ChatResponsePayload.from_wire(payload.to_wire()) == payload


def test_health_response_payload_projects_worker_model() -> None:
    worker = WorkerHealthPayload.from_health(
        WorkerHealth(
            name="memory",
            alive=True,
            last_success_at="now",
            consecutive_failures=0,
        )
    )

    assert HealthResponsePayload((worker,)).to_wire() == {
        "workers": [
            {
                "name": "memory",
                "alive": True,
                "last_success_at": "now",
                "last_error": None,
                "consecutive_failures": 0,
            }
        ]
    }
    assert MessagePayload("pong").to_wire() == {"message": "pong"}
    assert HealthResponsePayload.from_wire(
        HealthResponsePayload((worker,)).to_wire()
    ) == HealthResponsePayload((worker,))
    assert MessagePayload.from_wire(
        MessagePayload("pong").to_wire()
    ) == MessagePayload("pong")


@pytest.mark.parametrize(
    "payload, error",
    [
        (
            {
                "workers": [
                    {
                        "name": "memory",
                        "alive": "yes",
                        "last_success_at": None,
                        "last_error": None,
                        "consecutive_failures": 0,
                    }
                ]
            },
            r"worker\[0\].*alive",
        ),
        (
            {
                "answer": "answer",
                "reply": "answer",
                "thread_id": "default",
                "evidence_references": [1],
                "epistemic_status": "grounded",
            },
            "evidence_references",
        ),
        (
            {
                "answer": "answer",
                "reply": "answer",
                "thread_id": "default",
                "evidence_references": [],
                "epistemic_status": "invented",
            },
            "epistemic_status",
        ),
        (
            {
                "answer": "answer",
                "reply": "answer",
                "thread_id": "default",
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
        HealthResponsePayload.from_wire
        if "workers" in payload
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
    opened = ActivityOpenResponsePayload("sub-1")
    events = ActivityEventsResponsePayload((event,))
    closed = ActivityCloseResponsePayload(True)

    assert ActivityOpenResponsePayload.from_wire(
        opened.to_wire()
    ) == opened
    assert ActivityEventsResponsePayload.from_wire(
        events.to_wire()
    ) == events
    assert ActivityCloseResponsePayload.from_wire(
        closed.to_wire()
    ) == closed

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
            ActivityCloseRequestPayload.from_wire,
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
