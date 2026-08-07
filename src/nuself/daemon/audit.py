"""Typed observable projections of daemon lifecycle decisions."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from nuself.runtime.audit.definition import (
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata,
)
from nuself.runtime.audit.catalog import AuditCatalog

type DaemonLifecycleAuditEvent = Literal[
    "instance_lock_contended",
    "started",
    "stopped",
    "runtime_metadata_recovered",
    "start_requested",
    "start_completed",
    "start_failed",
    "stop_requested",
    "stop_completed",
    "stop_failed",
    "restart_requested",
    "restart_completed",
    "restart_failed",
]
_DAEMON_PHASES = frozenset(
    {"stopped", "owned_unready", "ready", "inconsistent", "unknown"}
)
_START_REASONS = frozenset(
    {"spawn_failed", "status_failed", "owner_unready", "process_exited", "timeout"}
)
_STOP_REASONS = frozenset(
    {"request_failed", "ownership_check_failed", "timeout"}
)

_MESSAGES: dict[DaemonLifecycleAuditEvent, str] = {
    "instance_lock_contended": (
        "daemon start rejected because this project already has an owner"
    ),
    "started": "daemon started",
    "stopped": "daemon stopped",
    "runtime_metadata_recovered": "stale daemon runtime metadata recovered",
    "start_requested": "daemon start requested",
    "start_completed": "daemon start completed",
    "start_failed": "daemon start failed",
    "stop_requested": "daemon stop requested",
    "stop_completed": "daemon stop completed",
    "stop_failed": "daemon stop failed",
    "restart_requested": "daemon restart requested",
    "restart_completed": "daemon restart completed",
    "restart_failed": "daemon restart failed",
}


def _validate_recovered_metadata(metadata: Mapping[str, object]) -> None:
    require_exact_metadata(metadata, frozenset({"socket", "pid"}))
    _require_bool(metadata, "socket")
    _require_bool(metadata, "pid")


def _validate_start_completed_metadata(
    metadata: Mapping[str, object],
) -> None:
    _validate_transition_metadata(
        metadata,
        outcomes=frozenset({"started", "already_ready"}),
        to_phase="ready",
    )


def _validate_stop_completed_metadata(
    metadata: Mapping[str, object],
) -> None:
    _validate_transition_metadata(
        metadata,
        outcomes=frozenset({"stopped", "already_stopped"}),
        to_phase="stopped",
    )


def _validate_transition_metadata(
    metadata: Mapping[str, object],
    *,
    outcomes: frozenset[str],
    to_phase: str,
) -> None:
    require_exact_metadata(
        metadata,
        frozenset(
            {
                "outcome",
                "changed",
                "from_phase",
                "to_phase",
                "pid",
                "socket",
            }
        ),
    )
    outcome = _require_string_choice(metadata, "outcome", outcomes)
    changed = _require_bool(metadata, "changed")
    _require_phase(metadata, "from_phase")
    actual_to_phase = _require_phase(metadata, "to_phase")
    if actual_to_phase != to_phase:
        raise AuditSchemaError(
            f"to_phase must be {to_phase!r}"
        )
    expected_changed = outcome in {"started", "stopped"}
    if changed is not expected_changed:
        raise AuditSchemaError(
            "changed does not match lifecycle outcome"
        )
    _require_optional_pid(metadata, "pid")
    _require_non_empty_string(metadata, "socket")


def _validate_start_failed_metadata(
    metadata: Mapping[str, object],
) -> None:
    _validate_start_failure_fields(metadata, stage=None)


def _validate_stop_failed_metadata(
    metadata: Mapping[str, object],
) -> None:
    _validate_stop_failure_fields(metadata, stage=None)


def _validate_restart_failed_metadata(
    metadata: Mapping[str, object],
) -> None:
    stage = metadata.get("stage")
    if stage == "start":
        _validate_start_failure_fields(metadata, stage="start")
        return
    if stage == "stop":
        _validate_stop_failure_fields(metadata, stage="stop")
        return
    raise AuditSchemaError(
        "restart_failed stage must be 'start' or 'stop'"
    )


def _validate_start_failure_fields(
    metadata: Mapping[str, object],
    *,
    stage: Literal["start"] | None,
) -> None:
    fields = {"reason", "phase", "pid", "socket", "exit_code"}
    if stage is not None:
        fields.add("stage")
    require_exact_metadata(metadata, frozenset(fields))
    _require_string_choice(metadata, "reason", _START_REASONS)
    _require_phase(metadata, "phase")
    _require_optional_pid(metadata, "pid")
    _require_non_empty_string(metadata, "socket")
    _require_optional_int(metadata, "exit_code")
    if stage is not None and metadata["stage"] != stage:
        raise AuditSchemaError(
            f"restart failure stage must be {stage!r}"
        )


def _validate_stop_failure_fields(
    metadata: Mapping[str, object],
    *,
    stage: Literal["stop"] | None,
) -> None:
    fields = {"reason", "phase", "pid", "socket", "owner_active"}
    if stage is not None:
        fields.add("stage")
    require_exact_metadata(metadata, frozenset(fields))
    _require_string_choice(metadata, "reason", _STOP_REASONS)
    _require_phase(metadata, "phase")
    _require_optional_pid(metadata, "pid")
    _require_non_empty_string(metadata, "socket")
    _require_optional_bool(metadata, "owner_active")
    if stage is not None and metadata["stage"] != stage:
        raise AuditSchemaError(
            f"restart failure stage must be {stage!r}"
        )


def _validate_restart_completed_metadata(
    metadata: Mapping[str, object],
) -> None:
    require_exact_metadata(
        metadata,
        frozenset(
            {
                "stop_outcome",
                "stop_changed",
                "stop_from_phase",
                "stop_to_phase",
                "start_outcome",
                "start_changed",
                "start_from_phase",
                "start_to_phase",
                "pid",
                "socket",
            }
        ),
    )
    stop_outcome = _require_string_choice(
        metadata,
        "stop_outcome",
        frozenset({"stopped", "already_stopped"}),
    )
    stop_changed = _require_bool(metadata, "stop_changed")
    _require_phase(metadata, "stop_from_phase")
    if _require_phase(metadata, "stop_to_phase") != "stopped":
        raise AuditSchemaError(
            "stop_to_phase must be 'stopped'"
        )
    start_outcome = _require_string_choice(
        metadata,
        "start_outcome",
        frozenset({"started", "already_ready"}),
    )
    start_changed = _require_bool(metadata, "start_changed")
    if _require_phase(metadata, "start_from_phase") != "stopped":
        raise AuditSchemaError(
            "start_from_phase must be 'stopped'"
        )
    if _require_phase(metadata, "start_to_phase") != "ready":
        raise AuditSchemaError(
            "start_to_phase must be 'ready'"
        )
    if stop_changed is not (stop_outcome == "stopped"):
        raise AuditSchemaError(
            "stop_changed does not match stop_outcome"
        )
    if start_changed is not (start_outcome == "started"):
        raise AuditSchemaError(
            "start_changed does not match start_outcome"
        )
    _require_optional_pid(metadata, "pid")
    _require_non_empty_string(metadata, "socket")


def _require_non_empty_string(
    metadata: Mapping[str, object],
    field: str,
) -> str:
    value = metadata[field]
    if not isinstance(value, str) or not value:
        raise AuditSchemaError(
            f"{field} must be a non-empty string"
        )
    return value


def _require_string_choice(
    metadata: Mapping[str, object],
    field: str,
    choices: frozenset[str],
) -> str:
    value = _require_non_empty_string(metadata, field)
    if value not in choices:
        raise AuditSchemaError(
            f"{field} must be one of {sorted(choices)!r}"
        )
    return value


def _require_phase(metadata: Mapping[str, object], field: str) -> str:
    return _require_string_choice(metadata, field, _DAEMON_PHASES)


def _require_bool(metadata: Mapping[str, object], field: str) -> bool:
    value = metadata[field]
    if type(value) is not bool:
        raise AuditSchemaError(f"{field} must be a boolean")
    return value


def _require_optional_bool(
    metadata: Mapping[str, object],
    field: str,
) -> bool | None:
    value = metadata[field]
    if value is not None and type(value) is not bool:
        raise AuditSchemaError(
            f"{field} must be a boolean or null"
        )
    return value


def _require_optional_int(
    metadata: Mapping[str, object],
    field: str,
) -> int | None:
    value = metadata[field]
    if value is not None and type(value) is not int:
        raise AuditSchemaError(
            f"{field} must be an integer or null"
        )
    return value


def _require_optional_pid(
    metadata: Mapping[str, object],
    field: str,
) -> int | None:
    value = _require_optional_int(metadata, field)
    if value is not None and value <= 0:
        raise AuditSchemaError(
            f"{field} must be positive or null"
        )
    return value


def _definitions() -> tuple[AuditEventDefinition, ...]:
    return (
        AuditEventDefinition(
            component="daemon",
            event="instance_lock_contended",
            level="warning",
            status="skipped",
            error_policy="required",
        ),
        AuditEventDefinition(
            component="daemon",
            event="started",
            level="info",
            status=None,
        ),
        AuditEventDefinition(
            component="daemon",
            event="stopped",
            level="info",
            status=None,
        ),
        AuditEventDefinition(
            component="daemon",
            event="runtime_metadata_recovered",
            level="info",
            status="recovered",
            metadata_validator=_validate_recovered_metadata,
        ),
        AuditEventDefinition(
            component="daemon",
            event="start_requested",
            level="info",
            status=None,
        ),
        AuditEventDefinition(
            component="daemon",
            event="start_completed",
            level="info",
            status="ready",
            metadata_validator=_validate_start_completed_metadata,
        ),
        AuditEventDefinition(
            component="daemon",
            event="start_failed",
            level="error",
            status="error",
            error_policy="required",
            metadata_validator=_validate_start_failed_metadata,
        ),
        AuditEventDefinition(
            component="daemon",
            event="stop_requested",
            level="info",
            status=None,
        ),
        AuditEventDefinition(
            component="daemon",
            event="stop_completed",
            level="info",
            status="stopped",
            metadata_validator=_validate_stop_completed_metadata,
        ),
        AuditEventDefinition(
            component="daemon",
            event="stop_failed",
            level="error",
            status="error",
            error_policy="required",
            metadata_validator=_validate_stop_failed_metadata,
        ),
        AuditEventDefinition(
            component="daemon",
            event="restart_requested",
            level="info",
            status=None,
        ),
        AuditEventDefinition(
            component="daemon",
            event="restart_completed",
            level="info",
            status="ready",
            metadata_validator=_validate_restart_completed_metadata,
        ),
        AuditEventDefinition(
            component="daemon",
            event="restart_failed",
            level="error",
            status="error",
            error_policy="required",
            metadata_validator=_validate_restart_failed_metadata,
        ),
    )


DAEMON_LIFECYCLE_AUDIT = AuditCatalog[DaemonLifecycleAuditEvent](
    _definitions(),
    _MESSAGES,
)


def write_lifecycle_audit(
    event: DaemonLifecycleAuditEvent,
    *,
    project_root: Path | None,
    error: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> None:
    """Validate and project one non-authoritative lifecycle decision."""

    audit_metadata: Mapping[str, object] = {} if metadata is None else metadata
    DAEMON_LIFECYCLE_AUDIT.write(
        event,
        project_root=project_root,
        error=error,
        metadata=dict(audit_metadata) or None,
    )
