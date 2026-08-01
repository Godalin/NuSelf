"""Closed audit schemas for the Reflection subsystem."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from nuself.logs import LogEvent
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata as _require_exact_fields,
)
from nuself.runtime.diagnostics import diagnostic_exception_chain
from nuself.runtime.observability import (
    report_observed_failure,
    write_observed_log_event,
)

ReflectionAuditEvent = Literal[
    "schedule_blocked",
    "cycle_started",
    "cycle_filtered",
    "cycle_discussion_rejected",
    "cycle_completed",
    "relevance_gate_fallback",
    "candidate_generation_skipped",
    "cycle_no_candidates",
    "candidate_generation_failed",
    "schedule_state_corrupt",
    "trace_recording_failed",
    "organizer_failed",
    "organizer_completed",
]

_IDEA_TYPES = frozenset(
    {"connection", "contradiction", "question", "action", "profile_update"}
)


def _require_non_empty_string(
    metadata: Mapping[str, object],
    field: str,
) -> str:
    value = metadata[field]
    if not isinstance(value, str) or not value:
        raise AuditSchemaError(f"audit metadata {field!r} must be non-empty")
    return value


def _validate_reason(metadata: Mapping[str, object]) -> None:
    _require_exact_fields(metadata, frozenset({"reason"}))
    _require_non_empty_string(metadata, "reason")


def _validate_reason_score(metadata: Mapping[str, object]) -> None:
    _require_exact_fields(metadata, frozenset({"reason", "score"}))
    _require_non_empty_string(metadata, "reason")
    _require_score(metadata, "score")


def _validate_completed(metadata: Mapping[str, object]) -> None:
    _require_exact_fields(
        metadata,
        frozenset({"reason", "score", "idea_type"}),
    )
    _require_non_empty_string(metadata, "reason")
    _require_score(metadata, "score")
    idea_type = _require_non_empty_string(metadata, "idea_type")
    if idea_type not in _IDEA_TYPES:
        raise AuditSchemaError("audit metadata 'idea_type' is invalid")


def _require_score(metadata: Mapping[str, object], field: str) -> None:
    value = metadata[field]
    if (
        not isinstance(value, float)
        or not 0.0 <= value <= 1.0
    ):
        raise AuditSchemaError(
            f"audit metadata {field!r} must be a float in [0, 1]"
        )


def _validate_record(metadata: Mapping[str, object]) -> None:
    _require_exact_fields(metadata, frozenset({"record"}))
    _require_non_empty_string(metadata, "record")


def _validate_reflection_id(metadata: Mapping[str, object]) -> None:
    _require_exact_fields(metadata, frozenset({"reflection_id"}))
    _require_non_empty_string(metadata, "reflection_id")


def _validate_organization(metadata: Mapping[str, object]) -> None:
    _require_exact_fields(
        metadata,
        frozenset({"merged_groups", "archived_entries"}),
    )
    for field in ("merged_groups", "archived_entries"):
        value = metadata[field]
        if type(value) is not int or value < 0:
            raise AuditSchemaError(
                f"audit metadata {field!r} must be a non-negative integer"
            )


def _build_registry() -> AuditDefinitionRegistry:
    definitions = (
        AuditEventDefinition(
            "reflection", "schedule_blocked", "info", "skipped",
            metadata_validator=_validate_reason,
        ),
        AuditEventDefinition(
            "reflection", "cycle_started", "info", "started",
        ),
        AuditEventDefinition(
            "reflection", "cycle_filtered", "info", "completed",
            metadata_validator=_validate_reason_score,
        ),
        AuditEventDefinition(
            "reflection", "cycle_discussion_rejected", "info", "completed",
            metadata_validator=_validate_reason,
        ),
        AuditEventDefinition(
            "reflection", "cycle_completed", "info", "completed",
            metadata_validator=_validate_completed,
        ),
        AuditEventDefinition(
            "reflection", "relevance_gate_fallback", "warning", "error",
        ),
        AuditEventDefinition(
            "reflection", "candidate_generation_skipped", "debug", "skipped",
            metadata_validator=_validate_reason,
        ),
        AuditEventDefinition(
            "reflection", "cycle_no_candidates", "info", "completed",
            metadata_validator=_validate_reason,
        ),
        AuditEventDefinition(
            "reflection", "candidate_generation_failed", "warning", "error",
            error_policy="required",
        ),
        AuditEventDefinition(
            "reflection", "schedule_state_corrupt", "warning", "degraded",
            error_policy="required",
            metadata_validator=_validate_record,
        ),
        AuditEventDefinition(
            "reflection", "trace_recording_failed", "error", "failed",
            error_policy="required",
            metadata_validator=_validate_reflection_id,
        ),
        AuditEventDefinition(
            "reflection", "organizer_failed", "error", "failed",
            error_policy="required",
        ),
        AuditEventDefinition(
            "reflection", "organizer_completed", "info", "completed",
            metadata_validator=_validate_organization,
        ),
    )
    registry = AuditDefinitionRegistry()
    for definition in definitions:
        registry.register(definition)
    return registry.seal()


REFLECTION_AUDIT_REGISTRY = _build_registry()


def write_reflection_audit(
    event: ReflectionAuditEvent,
    message: str,
    *,
    project_root: Path | None,
    metadata: dict[str, object] | None = None,
) -> LogEvent | None:
    """Validate and project one auxiliary Reflection audit."""

    definition = REFLECTION_AUDIT_REGISTRY.resolve("reflection", event)
    event_metadata = metadata or {}
    definition.validate(
        level=definition.level,
        status=definition.status,
        error=None,
        metadata=event_metadata,
    )
    return write_observed_log_event(
        definition.component,
        definition.event,
        message,
        project_root=project_root,
        level=definition.level,
        status=definition.status,
        metadata=dict(event_metadata),
    )


def report_reflection_failure(
    exc: Exception,
    *,
    event: ReflectionAuditEvent,
    message: str,
    project_root: Path | None,
    metadata: dict[str, object] | None = None,
) -> None:
    """Validate and report one caught Reflection failure."""

    definition = REFLECTION_AUDIT_REGISTRY.resolve("reflection", event)
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
