"""Closed audit contracts for Reason Output and its daemon worker."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from nuself.logs import LogEvent
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
)
from nuself.runtime.audit_types import LogComponent
from nuself.runtime.diagnostics import diagnostic_exception_chain
from nuself.runtime.observability import (
    report_observed_failure,
    write_observed_log_event,
)

ReasonOutputAuditEvent = Literal[
    "reason_output_planned",
    "reason_output_chunk_skipped",
    "reason_output_chunk_started",
    "reason_output_chunk_failed",
    "reason_output_chunk_completed",
    "reason_output_composed",
    "reason_output_pdf_started",
    "reason_output_pdf_timeout",
    "reason_output_pdf_failed",
    "reason_output_pdf_created",
    "export_job_enqueue_failed",
    "export_job_enqueued",
    "export_queue_drained",
    "export_worker_get_error",
    "export_job_type_ignored",
    "export_job_dequeued",
    "export_job_manifest_invalid",
    "export_job_progress_invalid",
    "export_job_composition_started",
    "export_job_state_persist_failed",
    "export_job_failed",
    "export_job_retry",
    "export_reconciliation_skip",
    "export_queue_reconciled",
]

_OUTPUT_MODES = frozenset({"outline", "narrative", "report", "summary"})


def _require_exact(
    metadata: Mapping[str, object],
    expected: frozenset[str],
) -> None:
    fields = set(metadata)
    if fields != set(expected):
        raise AuditSchemaError(
            "audit metadata fields differ "
            f"(missing={sorted(expected - fields)!r}, "
            f"extra={sorted(fields - expected)!r})"
        )


def _string(metadata: Mapping[str, object], field: str) -> str:
    value = metadata[field]
    if not isinstance(value, str) or not value:
        raise AuditSchemaError(f"audit metadata {field!r} must be non-empty")
    return value


def _integer(
    metadata: Mapping[str, object],
    field: str,
    *,
    positive: bool = False,
) -> int:
    value = metadata[field]
    if type(value) is not int or value < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise AuditSchemaError(
            f"audit metadata {field!r} must be a {qualifier} integer"
        )
    return value


def _optional_integer(
    metadata: Mapping[str, object],
    field: str,
) -> int | None:
    value = metadata[field]
    if value is None:
        return None
    return _integer(metadata, field)


def _identity(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"thread_id", "job_id"}))
    _string(metadata, "thread_id")
    _string(metadata, "job_id")


def _chunk_identity(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"thread_id", "job_id", "chunk_index"}),
    )
    _string(metadata, "thread_id")
    _string(metadata, "job_id")
    _integer(metadata, "chunk_index")


def _planned(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset(
            {
                "thread_id",
                "job_id",
                "mode",
                "output_format",
                "source_start_index",
                "source_end_index",
                "segment_size",
                "step_count",
            }
        ),
    )
    _string(metadata, "thread_id")
    _string(metadata, "job_id")
    if _string(metadata, "mode") not in _OUTPUT_MODES:
        raise AuditSchemaError("audit metadata 'mode' is invalid")
    if _string(metadata, "output_format") != "markdown":
        raise AuditSchemaError("audit metadata 'output_format' is invalid")
    start = _integer(metadata, "source_start_index")
    end = _optional_integer(metadata, "source_end_index")
    if end is not None and end < start:
        raise AuditSchemaError("audit source range is invalid")
    _integer(metadata, "segment_size", positive=True)
    _integer(metadata, "step_count", positive=True)


def _completed_chunk(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset(
            {"thread_id", "job_id", "chunk_index", "chunk_path"}
        ),
    )
    _string(metadata, "thread_id")
    _string(metadata, "job_id")
    _integer(metadata, "chunk_index")
    _string(metadata, "chunk_path")


def _composed(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"thread_id", "job_id", "chunk_count", "combined"}),
    )
    _string(metadata, "thread_id")
    _string(metadata, "job_id")
    _integer(metadata, "chunk_count", positive=True)
    _string(metadata, "combined")


def _paths(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"combined", "pdf"}))
    _string(metadata, "combined")
    _string(metadata, "pdf")


def _ignored_job(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"message_id", "job_name"}))
    _string(metadata, "message_id")
    _string(metadata, "job_name")


def _drained(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"drained_jobs"}))
    _integer(metadata, "drained_jobs", positive=True)


def _composition_started(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"thread_id", "job_id", "chunks"}),
    )
    _string(metadata, "thread_id")
    _string(metadata, "job_id")
    chunks = metadata["chunks"]
    if not (
        (type(chunks) is int and chunks >= 0)
        or chunks == "?"
    ):
        raise AuditSchemaError(
            "audit metadata 'chunks' must be non-negative or '?'"
        )


def _state_persist_failed(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"thread_id", "job_id", "operation_error"}),
    )
    _string(metadata, "thread_id")
    _string(metadata, "job_id")
    _string(metadata, "operation_error")


def _attempts(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"thread_id", "job_id", "attempts"}),
    )
    _string(metadata, "thread_id")
    _string(metadata, "job_id")
    _integer(metadata, "attempts", positive=True)


def _retry(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset(
            {"thread_id", "job_id", "attempts", "next_backoff"}
        ),
    )
    _string(metadata, "thread_id")
    _string(metadata, "job_id")
    _integer(metadata, "attempts", positive=True)
    _integer(metadata, "next_backoff", positive=True)


def _reconciled(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"replayed_jobs"}))
    _integer(metadata, "replayed_jobs")


def _build_registry() -> AuditDefinitionRegistry:
    definitions = (
        AuditEventDefinition(
            "reasoning", "reason_output_planned", "info", "created",
            metadata_validator=_planned,
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_chunk_skipped", "info", None,
            metadata_validator=_chunk_identity,
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_chunk_started", "info", None,
            metadata_validator=_chunk_identity,
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_chunk_failed", "error", "error",
            error_policy="required",
            metadata_validator=_chunk_identity,
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_chunk_completed", "info", "ok",
            duration_policy="required",
            metadata_validator=_completed_chunk,
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_composed", "info", "completed",
            metadata_validator=_composed,
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_pdf_started", "info", None,
            metadata_validator=_paths,
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_pdf_timeout", "warning", "error",
            metadata_validator=_paths,
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_pdf_failed", "warning", "error",
            error_policy="required",
            metadata_validator=_paths,
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_pdf_created", "info", "completed",
            metadata_validator=_paths,
        ),
        AuditEventDefinition(
            "daemon", "export_job_enqueue_failed", "warning", "degraded",
            error_policy="required",
            metadata_validator=_identity,
        ),
        AuditEventDefinition(
            "daemon", "export_job_enqueued", "info", "queued",
            metadata_validator=_identity,
        ),
        AuditEventDefinition(
            "daemon", "export_queue_drained", "warning", None,
            metadata_validator=_drained,
        ),
        AuditEventDefinition(
            "daemon", "export_worker_get_error", "warning", "error",
            error_policy="required",
        ),
        AuditEventDefinition(
            "daemon", "export_job_type_ignored", "warning", None,
            metadata_validator=_ignored_job,
        ),
        AuditEventDefinition(
            "daemon", "export_job_dequeued", "info", None,
            metadata_validator=_identity,
        ),
        AuditEventDefinition(
            "daemon", "export_job_manifest_invalid", "error", "error",
            error_policy="required",
            metadata_validator=_identity,
        ),
        AuditEventDefinition(
            "daemon", "export_job_progress_invalid", "warning", "degraded",
            error_policy="required",
            metadata_validator=_identity,
        ),
        AuditEventDefinition(
            "daemon", "export_job_composition_started", "info", None,
            metadata_validator=_composition_started,
        ),
        AuditEventDefinition(
            "daemon", "export_job_state_persist_failed", "error", "error",
            error_policy="required",
            metadata_validator=_state_persist_failed,
        ),
        AuditEventDefinition(
            "daemon", "export_job_failed", "error", "error",
            error_policy="required",
            metadata_validator=_attempts,
        ),
        AuditEventDefinition(
            "daemon", "export_job_retry", "info", "retry",
            metadata_validator=_retry,
        ),
        AuditEventDefinition(
            "daemon", "export_reconciliation_skip", "warning", "error",
            error_policy="required",
            metadata_validator=_identity,
        ),
        AuditEventDefinition(
            "daemon", "export_queue_reconciled", "info", None,
            metadata_validator=_reconciled,
        ),
    )
    registry = AuditDefinitionRegistry()
    for definition in definitions:
        registry.register(definition)
    return registry.seal()


REASON_OUTPUT_AUDIT_REGISTRY = _build_registry()


def write_reason_output_audit(
    component: LogComponent,
    event: ReasonOutputAuditEvent,
    message: str,
    *,
    project_root: Path | None,
    error: str | None = None,
    duration_ms: int | None = None,
    metadata: dict[str, object] | None = None,
    failure_event: str = "audit_projection_failed",
    failure_message: str = "Structured audit projection failed",
    failure_metadata: dict[str, object] | None = None,
) -> LogEvent | None:
    """Validate and project one auxiliary Reason Output audit."""

    definition = REASON_OUTPUT_AUDIT_REGISTRY.resolve(component, event)
    event_metadata = metadata or {}
    definition.validate(
        level=definition.level,
        status=definition.status,
        error=error,
        duration_ms=duration_ms,
        metadata=event_metadata,
    )
    return write_observed_log_event(
        definition.component,
        definition.event,
        message,
        project_root=project_root,
        level=definition.level,
        status=definition.status,
        error=error,
        duration_ms=duration_ms,
        metadata=dict(event_metadata),
        failure_event=failure_event,
        failure_message=failure_message,
        failure_metadata=failure_metadata,
    )


def write_export_worker_audit(
    event: ReasonOutputAuditEvent,
    message: str,
    *,
    project_root: Path,
    metadata: dict[str, object] | None = None,
) -> LogEvent | None:
    """Project one validated daemon-worker audit with its shared fallback."""

    return write_reason_output_audit(
        "daemon",
        event,
        message,
        project_root=project_root,
        metadata=metadata,
        failure_event="export_audit_write_failed",
        failure_message=f"Could not record export audit event {event}",
    )


def report_reason_output_failure(
    exc: Exception,
    *,
    component: LogComponent,
    event: ReasonOutputAuditEvent,
    message: str,
    project_root: Path | None,
    metadata: dict[str, object] | None = None,
) -> None:
    """Validate and report one caught Reason Output failure."""

    definition = REASON_OUTPUT_AUDIT_REGISTRY.resolve(component, event)
    event_metadata = metadata or {}
    status = definition.status
    if status is None:
        raise AuditSchemaError(
            f"{definition.component}/{definition.event} failure requires status"
        )
    definition.validate(
        level=definition.level,
        status=status,
        error=diagnostic_exception_chain(exc),
        metadata=event_metadata,
    )
    report_observed_failure(
        exc,
        component=definition.component,
        event=definition.event,
        message=message,
        project_root=project_root,
        level=definition.level,
        status=status,
        metadata=dict(event_metadata),
    )
