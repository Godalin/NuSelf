"""Closed audit contracts owned by the Memory subsystem."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from nuself.runtime.audit.definition import (
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata as _require_exact,
)
from nuself.runtime.audit.catalog import AuditCatalog

type MemoryAuditEvent = Literal[
    "curator_contended",
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
_FAILURE_MESSAGES: dict[MemoryAuditEvent, str] = {
    "auto_accept_failed": "Memory candidate auto-accept failed",
    "trace_recording_failed": "Memory trace recording failed",
    "curator_failed": "Memory curator failed",
    "post_chat_curation_failed": "Post-chat memory curation failed",
    "chat_trace_recording_failed": "Chat trace recording failed",
}

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


def _deferred(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset({"observation_id", "source_ref", "processed_messages"}),
    )
    _string(metadata, "observation_id")
    _string(metadata, "source_ref")
    if _integer(metadata, "processed_messages") != 0:
        raise AuditSchemaError(
            "curator deferred processed_messages must be zero"
        )


def _curator_contended(metadata: Mapping[str, object]) -> None:
    _require_exact(metadata, frozenset({"observation_id"}))
    _string(metadata, "observation_id")


def _curator_completed(metadata: Mapping[str, object]) -> None:
    _require_exact(
        metadata,
        frozenset(
            {
                "observation_id",
                "source_ref",
                "processed_messages",
                "created",
                "updated",
                "ignored",
            }
        ),
    )
    _string(metadata, "observation_id")
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


def _definitions() -> tuple[AuditEventDefinition, ...]:
    definitions = (
        AuditEventDefinition(
            "memory", "curator_contended", "info", "deferred",
            metadata_validator=_curator_contended,
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
    return definitions


MEMORY_AUDIT = AuditCatalog[MemoryAuditEvent](_definitions(), _FAILURE_MESSAGES)
