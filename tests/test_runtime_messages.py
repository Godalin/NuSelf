from __future__ import annotations

from collections.abc import Mapping

import pytest

from nuself.runtime import (
    RUNTIME_SCHEMA_VERSION,
    JobMessage,
    RuntimeContext,
    RuntimeEnvelope,
    current_runtime_context,
    runtime_context,
)


def test_runtime_context_is_nested_and_resets() -> None:
    assert current_runtime_context() == RuntimeContext()

    with runtime_context(request_id="req-1", source="daemon"):
        with runtime_context(turn_id="turn-1") as nested:
            assert nested == RuntimeContext(
                request_id="req-1",
                turn_id="turn-1",
                source="daemon",
            )
        assert current_runtime_context().turn_id is None

    assert current_runtime_context() == RuntimeContext()


def test_runtime_envelope_inherits_context_and_serializes_payload() -> None:
    with runtime_context(request_id="req-1"):
        envelope = RuntimeEnvelope(
            kind="event",
            name="worker.started",
            producer="daemon",
            payload={"workers": ["memory", "reflection"]},
        )

    record = envelope.to_record()
    assert record["schema_version"] == RUNTIME_SCHEMA_VERSION
    assert record["context"] == {"request_id": "req-1"}
    assert record["payload"] == {"workers": ["memory", "reflection"]}
    assert envelope.message_id


def test_runtime_envelope_payload_is_immutable() -> None:
    envelope = RuntimeEnvelope(
        kind="event",
        name="worker.started",
        producer="daemon",
        payload={"nested": {"status": "running"}},
    )
    nested = envelope.payload["nested"]
    assert isinstance(nested, Mapping)

    with pytest.raises(TypeError):
        nested["status"] = "stopped"  # type: ignore[index]


def test_runtime_envelope_rejects_non_json_payload() -> None:
    with pytest.raises(TypeError, match="not JSON-safe"):
        RuntimeEnvelope(
            kind="event",
            name="worker.started",
            producer="daemon",
            payload={"invalid": object()},
        )


def test_job_message_correlates_envelope_with_durable_job() -> None:
    with runtime_context(request_id="req-1"):
        message = JobMessage.create(
            name="reason.output.export",
            producer="reasoning",
            job_id="job-1",
            resource_id="thread-1",
        )

    assert message.envelope.kind == "job"
    assert message.envelope.context.request_id == "req-1"
    assert message.envelope.context.job_id == "job-1"
    assert message.job_id == "job-1"
    assert message.resource_id == "thread-1"
