"""Closed audit contracts owned by the Reason subsystem."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal, TypeVar

from nuself.logs import LogEvent
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata as _require_exact,
)
from nuself.runtime.observability import (
    report_defined_failure,
    run_observed_best_effort,
    write_observed_log_event,
)

ReasonAuditEvent = Literal[
    "proposal_created",
    "thread_started",
    "thread_status_changed",
    "thread_deleted",
    "advance_started",
    "advance_completed",
    "terminal_recommendation_applied",
    "trace_recording_failed",
    "scheduler_advance_failed",
    "scheduler_advance_completed",
    "llm_failover_suppressed_after_tool_call",
    "advance_failed",
    "completion_load_failed",
    "reason_output_planned",
    "reason_output_section_plan_fallback",
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
    "export_job_dequeued",
    "export_job_manifest_invalid",
    "export_job_progress_invalid",
    "export_job_composition_started",
    "export_job_state_persist_failed",
    "export_job_failed",
    "export_job_retry",
    "export_retry_schedule_failed",
    "export_retry_callback_failed",
    "export_reconciliation_skip",
    "export_queue_reconciled",
]
ReasonFailureEvent = Literal[
    "trace_recording_failed",
    "scheduler_advance_failed",
    "llm_failover_suppressed_after_tool_call",
    "advance_failed",
    "completion_load_failed",
    "reason_output_section_plan_fallback",
    "reason_output_chunk_failed",
    "reason_output_pdf_failed",
    "export_job_enqueue_failed",
    "export_worker_get_error",
    "export_job_manifest_invalid",
    "export_job_progress_invalid",
    "export_job_state_persist_failed",
    "export_job_failed",
    "export_retry_schedule_failed",
    "export_retry_callback_failed",
    "export_reconciliation_skip",
]

_OUTPUT_MODES = frozenset({"outline", "narrative", "report", "summary"})
_REASON_STATUSES = frozenset({"active", "paused", "resolved", "archived"})
_STEP_KINDS = frozenset(
    {
        "progress",
        "no_change",
        "question",
        "synthesis",
        "contradiction",
        "resolution",
        "planning",
    }
)
_TERMINAL_STATUSES = frozenset(
    {"continue", "suggest_resolved", "suggest_paused"}
)
_DAEMON_EVENTS = frozenset(
    {
        "export_job_enqueue_failed",
        "export_job_enqueued",
        "export_queue_drained",
        "export_worker_get_error",
        "export_job_dequeued",
        "export_job_manifest_invalid",
        "export_job_progress_invalid",
        "export_job_composition_started",
        "export_job_state_persist_failed",
        "export_job_failed",
        "export_job_retry",
        "export_retry_schedule_failed",
        "export_retry_callback_failed",
        "export_reconciliation_skip",
        "export_queue_reconciled",
    }
)

_MESSAGES: dict[ReasonAuditEvent, str] = {
    "proposal_created": "Reason thread proposal created",
    "thread_started": "Reason thread started",
    "thread_status_changed": "Reason thread status changed",
    "thread_deleted": "Reason thread deleted",
    "advance_started": "Reason advance started",
    "advance_completed": "Reason advance completed",
    "terminal_recommendation_applied": "Reason terminal recommendation applied",
    "trace_recording_failed": "Reason trace recording failed",
    "scheduler_advance_failed": "Reason scheduler advance failed",
    "scheduler_advance_completed": "Reason scheduler advance completed",
    "llm_failover_suppressed_after_tool_call": (
        "Reason endpoint failover suppressed after tool execution"
    ),
    "advance_failed": "Reason advance failed",
    "completion_load_failed": "Failed to load Reason thread completions",
    "reason_output_planned": "Reason output planned",
    "reason_output_section_plan_fallback": (
        "Reason output section planning used deterministic fallback"
    ),
    "reason_output_chunk_skipped": "Reason output chunk skipped",
    "reason_output_chunk_started": "Reason output chunk started",
    "reason_output_chunk_failed": "Reason output chunk failed",
    "reason_output_chunk_completed": "Reason output chunk completed",
    "reason_output_composed": "Reason output composed",
    "reason_output_pdf_started": "Reason output PDF generation started",
    "reason_output_pdf_timeout": "Reason output PDF generation timed out",
    "reason_output_pdf_failed": "Reason output PDF generation failed",
    "reason_output_pdf_created": "Reason output PDF created",
    "export_job_enqueue_failed": "Reason export job enqueue failed",
    "export_job_enqueued": "Reason export job enqueued",
    "export_queue_drained": "Reason export queue drained",
    "export_worker_get_error": "Reason export queue read failed",
    "export_job_dequeued": "Reason export job dequeued",
    "export_job_manifest_invalid": "Reason export manifest invalid",
    "export_job_progress_invalid": "Reason export progress invalid",
    "export_job_composition_started": "Reason export composition started",
    "export_job_state_persist_failed": (
        "Reason export failure state persistence failed"
    ),
    "export_job_failed": "Reason export job failed",
    "export_job_retry": "Reason export job retry scheduled",
    "export_retry_schedule_failed": (
        "Reason export retry scheduling failed"
    ),
    "export_retry_callback_failed": (
        "Reason export retry callback failed"
    ),
    "export_reconciliation_skip": "Reason export reconciliation skipped job",
    "export_queue_reconciled": "Reason export queue reconciled",
}

T = TypeVar("T")


def _string(metadata: Mapping[str, object], field: str) -> str:
    value = metadata[field]
    if not isinstance(value, str) or not value:
        raise AuditSchemaError(f"audit metadata {field!r} must be non-empty")
    return value


def _enum(
    metadata: Mapping[str, object],
    field: str,
    allowed: frozenset[str],
) -> str:
    value = _string(metadata, field)
    if value not in allowed:
        raise AuditSchemaError(f"audit metadata {field!r} is invalid")
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


def _thread_identity(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"thread_id"}))
    _string(metadata, "thread_id")


def _proposal(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"active_item_count", "mandate_count"}),
    )
    _integer(metadata, "active_item_count")
    _integer(metadata, "mandate_count")


def _thread_status(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"thread_id", "from_status", "to_status"}),
    )
    _string(metadata, "thread_id")
    before = _enum(metadata, "from_status", _REASON_STATUSES)
    after = _enum(metadata, "to_status", _REASON_STATUSES)
    if before == after:
        raise AuditSchemaError("reason status transition must change status")


def _advance_completed(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset(
            {
                "thread_id",
                "step_id",
                "step_kind",
                "new_findings",
                "new_pending",
                "retired_findings",
                "next_steps",
            }
        ),
    )
    _string(metadata, "thread_id")
    _string(metadata, "step_id")
    _enum(metadata, "step_kind", _STEP_KINDS)
    for field in (
        "new_findings",
        "new_pending",
        "retired_findings",
        "next_steps",
    ):
        _integer(metadata, field)


def _terminal_recommendation(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset(
            {
                "thread_id",
                "step_id",
                "terminal_status",
                "from_status",
                "to_status",
            }
        ),
    )
    _string(metadata, "thread_id")
    _string(metadata, "step_id")
    _enum(metadata, "terminal_status", _TERMINAL_STATUSES)
    before = _enum(metadata, "from_status", _REASON_STATUSES)
    after = _enum(metadata, "to_status", _REASON_STATUSES)
    if before == after:
        raise AuditSchemaError("terminal recommendation must change status")


def _trace_failure(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"operation", "thread_id", "step_id"}),
    )
    if _string(metadata, "operation") not in {
        "start_thread",
        "advance_thread",
    }:
        raise AuditSchemaError("reason trace operation is invalid")
    _string(metadata, "thread_id")
    step_id = metadata["step_id"]
    if step_id is not None and (
        not isinstance(step_id, str) or not step_id
    ):
        raise AuditSchemaError(
            "audit metadata 'step_id' must be non-empty or null"
        )


def _scheduler_completed(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"step_id", "step_kind"}))
    _string(metadata, "step_id")
    _enum(metadata, "step_kind", _STEP_KINDS)


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


def _output_mode(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"mode"}))
    _enum(metadata, "mode", _OUTPUT_MODES)


def _completed_chunk(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"thread_id", "job_id", "chunk_index"}),
    )
    _string(metadata, "thread_id")
    _string(metadata, "job_id")
    _integer(metadata, "chunk_index")


def _composed(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"thread_id", "job_id", "chunk_count"}),
    )
    _string(metadata, "thread_id")
    _string(metadata, "job_id")
    _integer(metadata, "chunk_count", positive=True)


def _drained(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"drained_jobs"}))
    _integer(metadata, "drained_jobs", positive=True)


def _composition_started(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"chunks"}))
    chunks = metadata["chunks"]
    if not (
        (type(chunks) is int and chunks >= 0)
        or chunks == "?"
    ):
        raise AuditSchemaError(
            "audit metadata 'chunks' must be non-negative or '?'"
        )


def _attempts(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"attempts"}))
    _integer(metadata, "attempts", positive=True)


def _retry(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"attempts", "next_backoff"}),
    )
    _integer(metadata, "attempts", positive=True)
    _integer(metadata, "next_backoff", positive=True)


def _reconciled(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"replayed_jobs"}))
    _integer(metadata, "replayed_jobs")


def _build_registry() -> AuditDefinitionRegistry:
    definitions = (
        AuditEventDefinition(
            "reasoning", "proposal_created", "info", None,
            metadata_validator=_proposal,
        ),
        AuditEventDefinition(
            "reasoning", "thread_started", "info", "created",
            metadata_validator=_thread_identity,
        ),
        AuditEventDefinition(
            "reasoning", "thread_status_changed", "info", "updated",
            metadata_validator=_thread_status,
        ),
        AuditEventDefinition(
            "reasoning", "thread_deleted", "info", "deleted",
            metadata_validator=_thread_identity,
        ),
        AuditEventDefinition(
            "reasoning", "advance_started", "info", "started",
            metadata_validator=_thread_identity,
        ),
        AuditEventDefinition(
            "reasoning", "advance_completed", "info", "completed",
            metadata_validator=_advance_completed,
        ),
        AuditEventDefinition(
            "reasoning", "terminal_recommendation_applied", "info", "updated",
            metadata_validator=_terminal_recommendation,
        ),
        AuditEventDefinition(
            "reasoning", "trace_recording_failed", "warning", "degraded",
            error_policy="required",
            metadata_validator=_trace_failure,
        ),
        AuditEventDefinition(
            "reasoning", "scheduler_advance_failed", "error", "error",
            error_policy="required",
        ),
        AuditEventDefinition(
            "reasoning", "scheduler_advance_completed", "info", "completed",
            metadata_validator=_scheduler_completed,
        ),
        AuditEventDefinition(
            "reasoning",
            "llm_failover_suppressed_after_tool_call",
            "warning",
            "failed",
            error_policy="required",
        ),
        AuditEventDefinition(
            "reasoning", "advance_failed", "error", "failed",
            error_policy="required",
        ),
        AuditEventDefinition(
            "reasoning", "completion_load_failed", "warning", "degraded",
            error_policy="required",
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_planned", "info", "created",
            metadata_validator=_planned,
        ),
        AuditEventDefinition(
            "reasoning",
            "reason_output_section_plan_fallback",
            "warning",
            "degraded",
            error_policy="required",
            metadata_validator=_output_mode,
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
            metadata_validator=_identity,
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_pdf_timeout", "warning", "error",
            metadata_validator=_identity,
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_pdf_failed", "warning", "error",
            error_policy="required",
            metadata_validator=_identity,
        ),
        AuditEventDefinition(
            "reasoning", "reason_output_pdf_created", "info", "completed",
            metadata_validator=_identity,
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
            "daemon", "export_job_dequeued", "info", None,
        ),
        AuditEventDefinition(
            "daemon", "export_job_manifest_invalid", "error", "error",
            error_policy="required",
        ),
        AuditEventDefinition(
            "daemon", "export_job_progress_invalid", "warning", "degraded",
            error_policy="required",
        ),
        AuditEventDefinition(
            "daemon", "export_job_composition_started", "info", None,
            metadata_validator=_composition_started,
        ),
        AuditEventDefinition(
            "daemon", "export_job_state_persist_failed", "error", "error",
            error_policy="required",
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
            "daemon", "export_retry_schedule_failed", "warning", "degraded",
            error_policy="required",
            metadata_validator=_retry,
        ),
        AuditEventDefinition(
            "daemon", "export_retry_callback_failed", "warning", "degraded",
            error_policy="required",
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


REASON_AUDIT_REGISTRY = _build_registry()


def _component(event: ReasonAuditEvent) -> Literal["daemon", "reasoning"]:
    return "daemon" if event in _DAEMON_EVENTS else "reasoning"


def write_reason_audit(
    event: ReasonAuditEvent,
    *,
    project_root: Path | None,
    error: str | None = None,
    duration_ms: int | None = None,
    metadata: dict[str, object] | None = None,
) -> LogEvent | None:
    """Validate and project one auxiliary Reason-owned audit."""

    definition = REASON_AUDIT_REGISTRY.resolve(_component(event), event)
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
        _MESSAGES[event],
        project_root=project_root,
        level=definition.level,
        status=definition.status,
        error=error,
        duration_ms=duration_ms,
        metadata=dict(event_metadata),
    )


def report_reason_failure(
    exc: BaseException,
    *,
    event: ReasonFailureEvent,
    project_root: Path | None,
    metadata: dict[str, object] | None = None,
) -> None:
    """Validate and report one caught Reason-owned failure."""

    definition = REASON_AUDIT_REGISTRY.resolve(_component(event), event)
    event_metadata = metadata or {}
    report_defined_failure(
        exc,
        definition=definition,
        message=_MESSAGES[event],
        project_root=project_root,
        metadata=dict(event_metadata),
    )


def run_reason_observed(
    operation: Callable[[], T],
    *,
    event: ReasonFailureEvent,
    project_root: Path | None,
    metadata: dict[str, object] | None = None,
    errors: tuple[type[Exception], ...] = (Exception,),
) -> T | None:
    """Run one auxiliary Reason effect under a registered failure schema."""

    definition = REASON_AUDIT_REGISTRY.resolve(_component(event), event)
    event_metadata = metadata or {}
    status = definition.status
    if status is None:
        raise AuditSchemaError(
            f"{definition.component}/{definition.event} failure requires status"
        )
    definition.validate(
        level=definition.level,
        status=status,
        error="caught failure",
        metadata=event_metadata,
    )
    return run_observed_best_effort(
        operation,
        component=definition.component,
        event=definition.event,
        message=_MESSAGES[event],
        project_root=project_root,
        metadata=dict(event_metadata),
        errors=errors,
        level=definition.level,
        status=status,
    )
