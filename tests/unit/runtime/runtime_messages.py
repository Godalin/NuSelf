from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import cast

import pytest

from nuself.reason.job_contracts import (
    REASON_OUTPUT_JOB_NAME,
    build_reason_job_definition_registry,
)
from nuself.runtime import (
    RUNTIME_SCHEMA_VERSION,
    JobMessage,
    MessageKind,
    RuntimeContext,
    RuntimeEnvelope,
    bind_runtime_context,
    current_runtime_context,
    decode_json_value,
    encode_json_value,
    runtime_context,
    use_runtime_context,
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


def test_saved_runtime_context_replaces_ambient_and_restores() -> None:
    saved = RuntimeContext(
        request_id="saved-request",
        job_id="saved-job",
        source="producer",
    )

    with runtime_context(
        request_id="ambient-request",
        conversation_id="ambient-thread",
        source="worker",
    ):
        with use_runtime_context(saved):
            assert current_runtime_context() == saved
        assert current_runtime_context() == RuntimeContext(
            request_id="ambient-request",
            conversation_id="ambient-thread",
            source="worker",
        )

    assert current_runtime_context() == RuntimeContext()


def test_bound_runtime_callback_captures_context_across_thread() -> None:
    observed: list[RuntimeContext] = []

    with runtime_context(
        request_id="captured-request",
        conversation_id="captured-thread",
        source="client",
    ):
        bound = bind_runtime_context(
            lambda: observed.append(current_runtime_context())
        )

    with runtime_context(request_id="invoker-request", source="test"):
        worker = threading.Thread(target=bound)
        worker.start()
        worker.join()
        assert current_runtime_context() == RuntimeContext(
            request_id="invoker-request",
            source="test",
        )

    assert observed == [
        RuntimeContext(
            request_id="captured-request",
            conversation_id="captured-thread",
            source="client",
        )
    ]


def test_bound_runtime_callback_restores_invoker_after_exception() -> None:
    def fail(value: str) -> None:
        assert value == "expected"
        assert current_runtime_context() == RuntimeContext(
            request_id="captured-request",
            source="client",
        )
        raise RuntimeError("callback failed")

    with runtime_context(request_id="captured-request", source="client"):
        bound = bind_runtime_context(fail)

    with runtime_context(request_id="invoker-request", source="test"):
        with pytest.raises(RuntimeError, match="callback failed"):
            bound("expected")
        assert current_runtime_context() == RuntimeContext(
            request_id="invoker-request",
            source="test",
        )

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


def test_runtime_envelope_round_trips_detached_record() -> None:
    envelope = RuntimeEnvelope(
        kind="event",
        name="worker.started",
        producer="daemon",
        message_id="event-1",
        created_at="2026-07-28T12:00:00+08:00",
        context=RuntimeContext(request_id="req-1"),
        payload={"nested": {"workers": ["memory"]}},
    )
    record = envelope.to_record()

    decoded = RuntimeEnvelope.from_record(record)

    assert decoded == envelope
    context = cast(dict[str, object], record["context"])
    payload = cast(dict[str, object], record["payload"])
    nested = cast(dict[str, object], payload["nested"])
    context["request_id"] = "changed"
    nested["workers"] = []
    assert decoded.context.request_id == "req-1"
    assert decoded.to_record()["payload"] == {
        "nested": {"workers": ["memory"]}
    }


def test_runtime_envelope_decodes_legacy_thread_context() -> None:
    record = RuntimeEnvelope(
        kind="job",
        name="legacy.chat",
        producer="test",
    ).to_record()
    record["context"] = {"thread_id": "legacy-chat"}

    decoded = RuntimeEnvelope.from_record(record)

    assert decoded.context.conversation_id == "legacy-chat"
    assert decoded.to_record()["context"] == {
        "conversation_id": "legacy-chat"
    }


def test_runtime_context_rejects_ambiguous_thread_alias() -> None:
    with pytest.raises(ValueError, match="both thread_id and conversation_id"):
        RuntimeContext.from_record(
            {
                "thread_id": "legacy-chat",
                "conversation_id": "current-chat",
            }
        )


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


def test_shared_json_codec_is_strict_and_canonical() -> None:
    assert encode_json_value(
        {"second": [2, 3], "first": 1},
        sort_keys=True,
        separators=(",", ":"),
    ) == '{"first":1,"second":[2,3]}'
    assert decode_json_value('{"items":[1,2]}') == {"items": [1, 2]}

    with pytest.raises(ValueError, match="non-standard JSON constant"):
        decode_json_value('{"value": Infinity}')


def test_runtime_envelope_rejects_non_json_payload() -> None:
    with pytest.raises(TypeError, match="not JSON-safe"):
        RuntimeEnvelope(
            kind="event",
            name="worker.started",
            producer="daemon",
            payload={"invalid": object()},
        )


@pytest.mark.parametrize(
    ("field_name", "value", "error_type"),
    (
        ("kind", "unknown", ValueError),
        ("schema_version", True, ValueError),
        ("schema_version", 2, ValueError),
        ("message_id", " ", ValueError),
        ("name", "", ValueError),
        ("producer", 42, ValueError),
        ("created_at", "2026-07-28T12:00:00", ValueError),
        ("created_at", "not-a-time", ValueError),
        ("context", [], TypeError),
        ("payload", [], TypeError),
    ),
)
def test_runtime_envelope_from_record_rejects_invalid_fields(
    field_name: str,
    value: object,
    error_type: type[Exception],
) -> None:
    record = RuntimeEnvelope(
        kind="event",
        name="worker.started",
        producer="daemon",
    ).to_record()
    record[field_name] = value

    with pytest.raises(error_type):
        RuntimeEnvelope.from_record(record)


def test_runtime_envelope_from_record_rejects_shape_drift() -> None:
    record = RuntimeEnvelope(
        kind="event",
        name="worker.started",
        producer="daemon",
    ).to_record()
    del record["payload"]
    record["unexpected"] = True

    with pytest.raises(
        ValueError,
        match="missing=.*payload.*unknown=.*unexpected",
    ):
        RuntimeEnvelope.from_record(record)


def test_runtime_envelope_local_construction_enforces_wire_invariants() -> None:
    with pytest.raises(ValueError, match="kind"):
        RuntimeEnvelope(
            kind=cast(MessageKind, "unknown"),
            name="worker.started",
            producer="daemon",
        )
    with pytest.raises(ValueError, match="schema version"):
        RuntimeEnvelope(
            kind="event",
            name="worker.started",
            producer="daemon",
            schema_version=True,
        )
    with pytest.raises(ValueError, match="include a timezone"):
        RuntimeEnvelope(
            kind="event",
            name="worker.started",
            producer="daemon",
            created_at="2026-07-28T12:00:00",
        )
    with pytest.raises(TypeError, match="context"):
        RuntimeEnvelope(
            kind="event",
            name="worker.started",
            producer="daemon",
            context=cast(RuntimeContext, []),
        )
    with pytest.raises(TypeError, match="payload"):
        RuntimeEnvelope(
            kind="event",
            name="worker.started",
            producer="daemon",
            payload=cast(Mapping[str, object], []),
        )


@pytest.mark.parametrize("kind", ("request", "notification"))
def test_runtime_envelope_rejects_unimplemented_kinds(
    kind: str,
) -> None:
    with pytest.raises(ValueError, match="kind is invalid"):
        RuntimeEnvelope(
            kind=cast(MessageKind, kind),
            name="unsupported",
            producer="test",
        )

    record = RuntimeEnvelope(
        kind="audit",
        name="supported",
        producer="test",
    ).to_record()
    record["kind"] = kind
    with pytest.raises(ValueError, match="kind is invalid"):
        RuntimeEnvelope.from_record(record)


@pytest.mark.parametrize("kind", ("event", "job", "audit"))
def test_runtime_envelope_accepts_complete_supported_taxonomy(
    kind: MessageKind,
) -> None:
    envelope = RuntimeEnvelope(
        kind=kind,
        name="supported",
        producer="test",
    )

    assert RuntimeEnvelope.from_record(envelope.to_record()).kind == kind


@pytest.mark.parametrize("value", (float("nan"), float("inf"), -float("inf")))
def test_runtime_envelope_rejects_non_finite_payload_float(
    value: float,
) -> None:
    with pytest.raises(TypeError, match="floats must be finite"):
        RuntimeEnvelope(
            kind="event",
            name="worker.started",
            producer="daemon",
            payload={"value": value},
        )


def test_runtime_envelope_rejects_non_string_payload_key() -> None:
    payload = cast(Mapping[str, object], {1: "one"})

    with pytest.raises(TypeError, match="keys must be strings"):
        RuntimeEnvelope(
            kind="event",
            name="worker.started",
            producer="daemon",
            payload=payload,
        )


def test_runtime_context_strictly_decodes_populated_fields() -> None:
    record: dict[str, object] = {
        "request_id": "req-1",
        "source": "daemon",
    }

    decoded = RuntimeContext.from_record(record)

    record["request_id"] = "changed"
    assert decoded == RuntimeContext(
        request_id="req-1",
        source="daemon",
    )


@pytest.mark.parametrize(
    "record",
    (
        {"request_id": ""},
        {"request_id": 42},
        {"unknown": "value"},
    ),
)
def test_runtime_context_rejects_invalid_record(
    record: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        RuntimeContext.from_record(record)


def test_runtime_context_rejects_blank_local_value() -> None:
    with pytest.raises(ValueError, match="request_id"):
        RuntimeContext(request_id=" ")


def test_job_message_correlates_envelope_with_durable_job() -> None:
    with runtime_context(request_id="req-1"):
        message = build_reason_job_definition_registry().create(
            name=REASON_OUTPUT_JOB_NAME,
            producer="daemon_retry",
            job_id="job-1",
            resource_id="thread-1",
            payload={"attempt": 2},
        )

    assert message.envelope.kind == "job"
    assert message.envelope.context.request_id == "req-1"
    assert message.envelope.context.job_id == "job-1"
    assert message.job_id == "job-1"
    assert message.resource_id == "thread-1"
    assert message.payload == {"attempt": 2}
    assert message.envelope.payload == {
        "resource_id": "thread-1",
        "data": {"attempt": 2},
    }


def test_job_message_envelope_round_trip_retains_routing() -> None:
    original = build_reason_job_definition_registry().create(
        name=REASON_OUTPUT_JOB_NAME,
        producer="daemon_retry",
        job_id="job-1",
        resource_id="thread-1",
        payload={"attempt": 3},
    )

    decoded = JobMessage(
        RuntimeEnvelope.from_record(original.envelope.to_record())
    )

    assert decoded.job_id == "job-1"
    assert decoded.resource_id == "thread-1"
    assert decoded.payload == {"attempt": 3}


def test_job_message_rejects_envelope_without_job_identity() -> None:
    envelope = RuntimeEnvelope(
        kind="job",
        name="reason.output.export",
        producer="reasoning",
        payload={"resource_id": "thread-1", "data": {}},
    )

    with pytest.raises(ValueError, match="requires job_id"):
        JobMessage(envelope)


def test_job_message_rejects_incomplete_or_extra_payload() -> None:
    context = RuntimeContext(job_id="job-1")
    payloads: tuple[dict[str, object], ...] = (
        {"resource_id": "thread-1"},
        {
            "resource_id": "thread-1",
            "data": {},
            "job_id": "duplicate",
        },
    )
    for payload in payloads:
        envelope = RuntimeEnvelope(
            kind="job",
            name="reason.output.export",
            producer="reasoning",
            context=context,
            payload=payload,
        )

        with pytest.raises(ValueError, match="fields are invalid"):
            JobMessage(envelope)
