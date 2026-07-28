from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from nuself.reason import output_audit
from nuself.runtime.audit_definitions import (
    AuditSchemaError,
    UnknownAuditDefinitionError,
)
from nuself.runtime.audit_types import LogComponent

_CANONICAL: tuple[
    tuple[str, str, dict[str, object], int | None],
    ...,
] = (
    (
        "reasoning",
        "reason_output_planned",
        {
            "thread_id": "thread-1",
            "job_id": "job-1",
            "mode": "narrative",
            "output_format": "markdown",
            "source_start_index": 0,
            "source_end_index": None,
            "segment_size": 5,
            "step_count": 2,
        },
        None,
    ),
    (
        "reasoning",
        "reason_output_chunk_skipped",
        {"thread_id": "thread-1", "job_id": "job-1", "chunk_index": 0},
        None,
    ),
    (
        "reasoning",
        "reason_output_chunk_started",
        {"thread_id": "thread-1", "job_id": "job-1", "chunk_index": 0},
        None,
    ),
    (
        "reasoning",
        "reason_output_chunk_failed",
        {"thread_id": "thread-1", "job_id": "job-1", "chunk_index": 0},
        None,
    ),
    (
        "reasoning",
        "reason_output_chunk_completed",
        {
            "thread_id": "thread-1",
            "job_id": "job-1",
            "chunk_index": 0,
            "chunk_path": "/private/chunk.md",
        },
        12,
    ),
    (
        "reasoning",
        "reason_output_composed",
        {
            "thread_id": "thread-1",
            "job_id": "job-1",
            "chunk_count": 2,
            "combined": "/private/combined.md",
        },
        None,
    ),
    (
        "reasoning",
        "reason_output_pdf_started",
        {"combined": "/private/combined.md", "pdf": "/private/output.pdf"},
        None,
    ),
    (
        "reasoning",
        "reason_output_pdf_timeout",
        {"combined": "/private/combined.md", "pdf": "/private/output.pdf"},
        None,
    ),
    (
        "reasoning",
        "reason_output_pdf_failed",
        {"combined": "/private/combined.md", "pdf": "/private/output.pdf"},
        None,
    ),
    (
        "reasoning",
        "reason_output_pdf_created",
        {"combined": "/private/combined.md", "pdf": "/private/output.pdf"},
        None,
    ),
    (
        "daemon",
        "export_job_enqueue_failed",
        {"thread_id": "thread-1", "job_id": "job-1"},
        None,
    ),
    (
        "daemon",
        "export_job_enqueued",
        {"thread_id": "thread-1", "job_id": "job-1"},
        None,
    ),
    ("daemon", "export_queue_drained", {"drained_jobs": 2}, None),
    ("daemon", "export_worker_get_error", {}, None),
    (
        "daemon",
        "export_job_type_ignored",
        {"message_id": "message-1", "job_name": "other.job"},
        None,
    ),
    (
        "daemon",
        "export_job_dequeued",
        {"thread_id": "thread-1", "job_id": "job-1"},
        None,
    ),
    (
        "daemon",
        "export_job_manifest_invalid",
        {"thread_id": "thread-1", "job_id": "job-1"},
        None,
    ),
    (
        "daemon",
        "export_job_progress_invalid",
        {"thread_id": "thread-1", "job_id": "job-1"},
        None,
    ),
    (
        "daemon",
        "export_job_composition_started",
        {"thread_id": "thread-1", "job_id": "job-1", "chunks": "?"},
        None,
    ),
    (
        "daemon",
        "export_job_state_persist_failed",
        {
            "thread_id": "thread-1",
            "job_id": "job-1",
            "operation_error": "runner failed",
        },
        None,
    ),
    (
        "daemon",
        "export_job_failed",
        {"thread_id": "thread-1", "job_id": "job-1", "attempts": 5},
        None,
    ),
    (
        "daemon",
        "export_job_retry",
        {
            "thread_id": "thread-1",
            "job_id": "job-1",
            "attempts": 1,
            "next_backoff": 10,
        },
        None,
    ),
    (
        "daemon",
        "export_reconciliation_skip",
        {"thread_id": "thread-1", "job_id": "job-1"},
        None,
    ),
    ("daemon", "export_queue_reconciled", {"replayed_jobs": 0}, None),
)


def test_reason_output_audit_registry_owns_complete_taxonomy() -> None:
    assert {
        (definition.component, definition.event)
        for definition in output_audit.REASON_OUTPUT_AUDIT_REGISTRY.definitions
    } == {
        (component, event)
        for component, event, _, _ in _CANONICAL
    }


@pytest.mark.parametrize(
    ("component", "event", "metadata", "duration_ms"),
    _CANONICAL,
)
def test_reason_output_audit_definitions_accept_canonical_payloads(
    component: str,
    event: str,
    metadata: dict[str, object],
    duration_ms: int | None,
) -> None:
    definition = output_audit.REASON_OUTPUT_AUDIT_REGISTRY.resolve(
        cast(LogComponent, component),
        event,
    )

    definition.validate(
        level=definition.level,
        status=definition.status,
        error=(
            "caught failure"
            if definition.error_policy == "required"
            else None
        ),
        duration_ms=duration_ms,
        metadata=metadata,
    )


@pytest.mark.parametrize(
    ("component", "event", "metadata", "duration_ms"),
    _CANONICAL,
)
def test_reason_output_audit_definitions_reject_unknown_metadata(
    component: str,
    event: str,
    metadata: dict[str, object],
    duration_ms: int | None,
) -> None:
    definition = output_audit.REASON_OUTPUT_AUDIT_REGISTRY.resolve(
        cast(LogComponent, component),
        event,
    )

    with pytest.raises(AuditSchemaError, match="metadata"):
        definition.validate(
            level=definition.level,
            status=definition.status,
            error=(
                "caught failure"
                if definition.error_policy == "required"
                else None
            ),
            duration_ms=duration_ms,
            metadata={**metadata, "unexpected": True},
        )


def test_reason_output_audit_rejects_unknown_event_before_sink(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sink_calls = 0

    def unexpected_sink(*args: object, **kwargs: object) -> None:
        nonlocal sink_calls
        sink_calls += 1

    monkeypatch.setattr(
        output_audit,
        "write_observed_log_event",
        unexpected_sink,
    )

    with pytest.raises(UnknownAuditDefinitionError):
        output_audit.write_reason_output_audit(
            "reasoning",
            cast(output_audit.ReasonOutputAuditEvent, "reason_output_done"),
            "invalid",
            project_root=tmp_path,
        )

    assert sink_calls == 0
