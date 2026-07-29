"""Closed audit contracts owned by the Memory subsystem."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal, TypeVar

from nuself.logs import LogEvent
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
)
from nuself.runtime.diagnostics import diagnostic_exception_chain
from nuself.runtime.observability import (
    report_observed_failure,
    run_observed_best_effort,
    write_observed_log_event,
)

MemoryAuditEvent = Literal[
    "curator_history_gap",
    "curator_deferred",
    "curator_completed",
    "candidate_merged",
    "candidate_created",
    "candidate_updated",
    "optimizer_deferred",
    "optimizer_completed",
    "optimizer_candidate_staged",
    "auto_accept_failed",
    "trace_recording_failed",
    "curator_failed",
    "post_chat_curation_failed",
    "chat_trace_recording_failed",
]
MemoryFailureEvent = Literal[
    "auto_accept_failed",
    "trace_recording_failed",
    "curator_failed",
    "post_chat_curation_failed",
    "chat_trace_recording_failed",
]

_FAILURE_MESSAGES: dict[MemoryFailureEvent, str] = {
    "auto_accept_failed": "Memory candidate auto-accept failed",
    "trace_recording_failed": "Memory trace recording failed",
    "curator_failed": "Memory curator failed",
    "post_chat_curation_failed": "Post-chat memory curation failed",
    "chat_trace_recording_failed": "Chat trace recording failed",
}

T = TypeVar("T")


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


def _integer(metadata: Mapping[str, object], field: str) -> int:
    value = metadata[field]
    if type(value) is not int or value < 0:
        raise AuditSchemaError(
            f"audit metadata {field!r} must be a non-negative integer"
        )
    return value


def _history_gap(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"thread_id", "cursor", "visible_start"}),
    )
    _string(metadata, "thread_id")
    cursor = _integer(metadata, "cursor")
    visible_start = _integer(metadata, "visible_start")
    if cursor >= visible_start:
        raise AuditSchemaError("curator history gap range is invalid")


def _deferred(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"thread_id", "source_ref", "processed_messages"}),
    )
    _string(metadata, "thread_id")
    _string(metadata, "source_ref")
    if _integer(metadata, "processed_messages") != 0:
        raise AuditSchemaError(
            "curator deferred processed_messages must be zero"
        )


def _curator_completed(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset(
            {
                "thread_id",
                "source_ref",
                "processed_messages",
                "created",
                "updated",
                "ignored",
            }
        ),
    )
    _string(metadata, "thread_id")
    _string(metadata, "source_ref")
    if _integer(metadata, "processed_messages") < 1:
        raise AuditSchemaError(
            "curator completed processed_messages must be positive"
        )
    for field in ("created", "updated", "ignored"):
        _integer(metadata, field)


def _candidate_created(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"candidate_id", "memory_type"}))
    _string(metadata, "candidate_id")
    _string(metadata, "memory_type")


def _candidate_targeted(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"candidate_id", "target_entry_id", "memory_type"}),
    )
    _string(metadata, "candidate_id")
    _string(metadata, "target_entry_id")
    _string(metadata, "memory_type")


def _optimizer_deferred(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"reviewed"}))
    if _integer(metadata, "reviewed") != 0:
        raise AuditSchemaError("optimizer deferred reviewed must be zero")


def _optimizer_completed(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"reviewed", "updated", "deleted", "ignored"}),
    )
    if _integer(metadata, "reviewed") < 1:
        raise AuditSchemaError("optimizer completed reviewed must be positive")
    for field in ("updated", "deleted", "ignored"):
        _integer(metadata, field)


def _optimizer_candidate(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"action", "candidate_id", "target_entry_id"}),
    )
    action = _string(metadata, "action")
    if action not in {"update", "delete"}:
        raise AuditSchemaError("optimizer candidate action is invalid")
    _string(metadata, "candidate_id")
    _string(metadata, "target_entry_id")


def _auto_accept_failed(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset(
            {"candidate_id", "action", "memory_type", "target_entry_id"}
        ),
    )
    _string(metadata, "candidate_id")
    action = _string(metadata, "action")
    if action not in {"create", "update"}:
        raise AuditSchemaError("auto-accept action is invalid")
    _string(metadata, "memory_type")
    target = metadata["target_entry_id"]
    if target is not None and (not isinstance(target, str) or not target):
        raise AuditSchemaError(
            "audit metadata 'target_entry_id' must be non-empty or null"
        )


def _trace_failed(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"memory_id", "action"}))
    _string(metadata, "memory_id")
    if _string(metadata, "action") not in {
        "create",
        "update",
        "add",
        "accept",
        "merge",
        "import",
    }:
        raise AuditSchemaError("memory trace action is invalid")


def _build_registry() -> AuditDefinitionRegistry:
    definitions = (
        AuditEventDefinition(
            "memory", "curator_history_gap", "warning", "degraded",
            metadata_validator=_history_gap,
        ),
        AuditEventDefinition(
            "memory", "curator_deferred", "info", "deferred",
            metadata_validator=_deferred,
        ),
        AuditEventDefinition(
            "memory", "curator_completed", "info", "completed",
            metadata_validator=_curator_completed,
        ),
        AuditEventDefinition(
            "memory", "candidate_merged", "info", "created",
            metadata_validator=_candidate_targeted,
        ),
        AuditEventDefinition(
            "memory", "candidate_created", "info", "created",
            metadata_validator=_candidate_created,
        ),
        AuditEventDefinition(
            "memory", "candidate_updated", "info", "created",
            metadata_validator=_candidate_targeted,
        ),
        AuditEventDefinition(
            "memory", "optimizer_deferred", "info", None,
            metadata_validator=_optimizer_deferred,
        ),
        AuditEventDefinition(
            "memory", "optimizer_completed", "info", None,
            metadata_validator=_optimizer_completed,
        ),
        AuditEventDefinition(
            "memory", "optimizer_candidate_staged", "info", None,
            metadata_validator=_optimizer_candidate,
        ),
        AuditEventDefinition(
            "memory", "auto_accept_failed", "warning", "degraded",
            error_policy="required",
            metadata_validator=_auto_accept_failed,
        ),
        AuditEventDefinition(
            "memory", "trace_recording_failed", "warning", "degraded",
            error_policy="required",
            metadata_validator=_trace_failed,
        ),
        AuditEventDefinition(
            "memory", "curator_failed", "error", "error",
            error_policy="required",
        ),
        AuditEventDefinition(
            "memory", "post_chat_curation_failed", "warning", "degraded",
            error_policy="required",
        ),
        AuditEventDefinition(
            "memory", "chat_trace_recording_failed", "warning", "degraded",
            error_policy="required",
        ),
    )
    registry = AuditDefinitionRegistry()
    for definition in definitions:
        registry.register(definition)
    return registry.seal()


MEMORY_AUDIT_REGISTRY = _build_registry()


def _write_memory_audit(
    event: MemoryAuditEvent,
    message: str,
    *,
    project_root: Path | None,
    metadata: dict[str, object] | None,
) -> LogEvent | None:
    definition = MEMORY_AUDIT_REGISTRY.resolve("memory", event)
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


def write_curator_audit(
    event: MemoryAuditEvent,
    message: str,
    *,
    project_root: Path,
    metadata: dict[str, object] | None = None,
) -> LogEvent | None:
    """Validate and project one curator audit."""

    return _write_memory_audit(
        event,
        message,
        project_root=project_root,
        metadata=metadata,
    )


def write_optimizer_audit(
    event: MemoryAuditEvent,
    message: str,
    *,
    project_root: Path,
    metadata: dict[str, object] | None = None,
) -> LogEvent | None:
    """Validate and project one optimizer audit."""

    return _write_memory_audit(
        event,
        message,
        project_root=project_root,
        metadata=metadata,
    )


def run_memory_observed(
    operation: Callable[[], T],
    *,
    event: MemoryFailureEvent,
    project_root: Path | None,
    metadata: dict[str, object],
    errors: tuple[type[Exception], ...] = (Exception,),
) -> T | None:
    """Run one secondary curation effect under a registered failure schema."""

    definition = MEMORY_AUDIT_REGISTRY.resolve("memory", event)
    status = definition.status
    if status is None:
        raise AuditSchemaError(
            f"{definition.component}/{definition.event} failure requires status"
        )
    definition.validate(
        level=definition.level,
        status=status,
        error="caught failure",
        metadata=metadata,
    )
    return run_observed_best_effort(
        operation,
        component=definition.component,
        event=definition.event,
        message=_FAILURE_MESSAGES[event],
        project_root=project_root,
        metadata=dict(metadata),
        errors=errors,
        level=definition.level,
        status=status,
    )


def report_memory_failure(
    exc: Exception,
    *,
    event: MemoryFailureEvent,
    project_root: Path | None,
    metadata: dict[str, object] | None = None,
) -> None:
    """Validate and report one caught Memory-owned failure."""

    definition = MEMORY_AUDIT_REGISTRY.resolve("memory", event)
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
        message=_FAILURE_MESSAGES[event],
        project_root=project_root,
        metadata=dict(event_metadata),
        level=definition.level,
        status=status,
    )
