"""Closed audit schemas for the Reflection subsystem."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from nuself.runtime.audit.definition import (
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata as _require_exact_fields,
)
from nuself.runtime.audit.catalog import AuditCatalog

type ReflectionAuditEvent = Literal[
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
    "notification_provenance_failed",
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


def _definitions() -> tuple[AuditEventDefinition, ...]:
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
            "reflection", "notification_provenance_failed", "warning", "degraded",
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
    return definitions


REFLECTION_AUDIT = AuditCatalog[ReflectionAuditEvent](_definitions())
