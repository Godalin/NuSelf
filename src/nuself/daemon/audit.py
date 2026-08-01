"""Typed observable projections of daemon lifecycle decisions."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from nuself.runtime.audit_types import LogLevel
from nuself.runtime.definitions import (
    DefinitionRegistry,
    UnknownDefinitionError,
)
from nuself.runtime.identities import require_audit_event_name
from nuself.runtime.observability import write_observed_log_event

DaemonLifecycleAuditEvent = Literal[
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
ErrorPolicy = Literal["forbidden", "required"]
MetadataValidator = Callable[[Mapping[str, object]], None]

_DAEMON_PHASES = frozenset(
    {"stopped", "owned_unready", "ready", "inconsistent", "unknown"}
)
_START_REASONS = frozenset(
    {"spawn_failed", "status_failed", "owner_unready", "process_exited", "timeout"}
)
_STOP_REASONS = frozenset(
    {"request_failed", "ownership_check_failed", "timeout"}
)


class DaemonLifecycleAuditSchemaError(ValueError):
    """A lifecycle audit producer violated its registered contract."""


def _validate_no_metadata(metadata: Mapping[str, object]) -> None:
    _require_exact_fields(metadata, frozenset())


@dataclass(frozen=True)
class DaemonLifecycleAuditDefinition:
    """Closed projection defaults and payload contract for one event."""

    event: DaemonLifecycleAuditEvent
    message: str
    level: LogLevel = "info"
    status: str | None = None
    error_policy: ErrorPolicy = "forbidden"
    metadata_validator: MetadataValidator = _validate_no_metadata

    def __post_init__(self) -> None:
        require_audit_event_name(self.event)
        if not self.message:
            raise ValueError("lifecycle audit message must not be empty")
        if self.error_policy not in {"forbidden", "required"}:
            raise ValueError("lifecycle audit error policy is invalid")
        if not callable(self.metadata_validator):
            raise TypeError(
                "lifecycle audit metadata validator must be callable"
            )

    def validate(
        self,
        *,
        error: str | None,
        metadata: Mapping[str, object],
    ) -> None:
        if self.error_policy == "required":
            if not isinstance(error, str) or not error:
                raise DaemonLifecycleAuditSchemaError(
                    f"{self.event} requires a non-empty error"
                )
        elif error is not None:
            raise DaemonLifecycleAuditSchemaError(
                f"{self.event} forbids an error"
            )
        self.metadata_validator(metadata)


def _validate_recovered_metadata(metadata: Mapping[str, object]) -> None:
    _require_exact_fields(metadata, frozenset({"socket", "pid"}))
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
    _require_exact_fields(
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
        raise DaemonLifecycleAuditSchemaError(
            f"to_phase must be {to_phase!r}"
        )
    expected_changed = outcome in {"started", "stopped"}
    if changed is not expected_changed:
        raise DaemonLifecycleAuditSchemaError(
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
    raise DaemonLifecycleAuditSchemaError(
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
    _require_exact_fields(metadata, frozenset(fields))
    _require_string_choice(metadata, "reason", _START_REASONS)
    _require_phase(metadata, "phase")
    _require_optional_pid(metadata, "pid")
    _require_non_empty_string(metadata, "socket")
    _require_optional_int(metadata, "exit_code")
    if stage is not None and metadata["stage"] != stage:
        raise DaemonLifecycleAuditSchemaError(
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
    _require_exact_fields(metadata, frozenset(fields))
    _require_string_choice(metadata, "reason", _STOP_REASONS)
    _require_phase(metadata, "phase")
    _require_optional_pid(metadata, "pid")
    _require_non_empty_string(metadata, "socket")
    _require_optional_bool(metadata, "owner_active")
    if stage is not None and metadata["stage"] != stage:
        raise DaemonLifecycleAuditSchemaError(
            f"restart failure stage must be {stage!r}"
        )


def _validate_restart_completed_metadata(
    metadata: Mapping[str, object],
) -> None:
    _require_exact_fields(
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
        raise DaemonLifecycleAuditSchemaError(
            "stop_to_phase must be 'stopped'"
        )
    start_outcome = _require_string_choice(
        metadata,
        "start_outcome",
        frozenset({"started", "already_ready"}),
    )
    start_changed = _require_bool(metadata, "start_changed")
    if _require_phase(metadata, "start_from_phase") != "stopped":
        raise DaemonLifecycleAuditSchemaError(
            "start_from_phase must be 'stopped'"
        )
    if _require_phase(metadata, "start_to_phase") != "ready":
        raise DaemonLifecycleAuditSchemaError(
            "start_to_phase must be 'ready'"
        )
    if stop_changed is not (stop_outcome == "stopped"):
        raise DaemonLifecycleAuditSchemaError(
            "stop_changed does not match stop_outcome"
        )
    if start_changed is not (start_outcome == "started"):
        raise DaemonLifecycleAuditSchemaError(
            "start_changed does not match start_outcome"
        )
    _require_optional_pid(metadata, "pid")
    _require_non_empty_string(metadata, "socket")


def _require_exact_fields(
    metadata: Mapping[str, object],
    expected: frozenset[str],
) -> None:
    runtime_metadata = cast(Mapping[object, object], metadata)
    if any(not isinstance(field, str) for field in runtime_metadata):
        raise DaemonLifecycleAuditSchemaError(
            "lifecycle audit metadata field names must be strings"
        )
    actual = frozenset(metadata)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise DaemonLifecycleAuditSchemaError(
            f"lifecycle audit metadata fields differ: "
            f"missing={missing!r}, extra={extra!r}"
        )


def _require_non_empty_string(
    metadata: Mapping[str, object],
    field: str,
) -> str:
    value = metadata[field]
    if not isinstance(value, str) or not value:
        raise DaemonLifecycleAuditSchemaError(
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
        raise DaemonLifecycleAuditSchemaError(
            f"{field} must be one of {sorted(choices)!r}"
        )
    return value


def _require_phase(metadata: Mapping[str, object], field: str) -> str:
    return _require_string_choice(metadata, field, _DAEMON_PHASES)


def _require_bool(metadata: Mapping[str, object], field: str) -> bool:
    value = metadata[field]
    if type(value) is not bool:
        raise DaemonLifecycleAuditSchemaError(f"{field} must be a boolean")
    return value


def _require_optional_bool(
    metadata: Mapping[str, object],
    field: str,
) -> bool | None:
    value = metadata[field]
    if value is not None and type(value) is not bool:
        raise DaemonLifecycleAuditSchemaError(
            f"{field} must be a boolean or null"
        )
    return value


def _require_optional_int(
    metadata: Mapping[str, object],
    field: str,
) -> int | None:
    value = metadata[field]
    if value is not None and type(value) is not int:
        raise DaemonLifecycleAuditSchemaError(
            f"{field} must be an integer or null"
        )
    return value


def _require_optional_pid(
    metadata: Mapping[str, object],
    field: str,
) -> int | None:
    value = _require_optional_int(metadata, field)
    if value is not None and value <= 0:
        raise DaemonLifecycleAuditSchemaError(
            f"{field} must be positive or null"
        )
    return value


def _build_definition_registry(
    definitions: tuple[DaemonLifecycleAuditDefinition, ...],
) -> DefinitionRegistry[
    DaemonLifecycleAuditEvent,
    DaemonLifecycleAuditDefinition,
]:
    registry = DefinitionRegistry[
        DaemonLifecycleAuditEvent,
        DaemonLifecycleAuditDefinition,
    ](
        lambda definition: definition.event,
        namespace="daemon lifecycle audit",
    )
    for definition in definitions:
        registry.register(definition)
    return registry.seal()


DAEMON_LIFECYCLE_AUDIT_REGISTRY = _build_definition_registry(
    (
        DaemonLifecycleAuditDefinition(
            event="instance_lock_contended",
            message=(
                "daemon start rejected because this project already has an owner"
            ),
            level="warning",
            status="skipped",
            error_policy="required",
        ),
        DaemonLifecycleAuditDefinition(
            event="started",
            message="daemon started",
        ),
        DaemonLifecycleAuditDefinition(
            event="stopped",
            message="daemon stopped",
        ),
        DaemonLifecycleAuditDefinition(
            event="runtime_metadata_recovered",
            message="stale daemon runtime metadata recovered",
            status="recovered",
            metadata_validator=_validate_recovered_metadata,
        ),
        DaemonLifecycleAuditDefinition(
            event="start_requested",
            message="daemon start requested",
        ),
        DaemonLifecycleAuditDefinition(
            event="start_completed",
            message="daemon start completed",
            status="ready",
            metadata_validator=_validate_start_completed_metadata,
        ),
        DaemonLifecycleAuditDefinition(
            event="start_failed",
            message="daemon start failed",
            level="error",
            status="error",
            error_policy="required",
            metadata_validator=_validate_start_failed_metadata,
        ),
        DaemonLifecycleAuditDefinition(
            event="stop_requested",
            message="daemon stop requested",
        ),
        DaemonLifecycleAuditDefinition(
            event="stop_completed",
            message="daemon stop completed",
            status="stopped",
            metadata_validator=_validate_stop_completed_metadata,
        ),
        DaemonLifecycleAuditDefinition(
            event="stop_failed",
            message="daemon stop failed",
            level="error",
            status="error",
            error_policy="required",
            metadata_validator=_validate_stop_failed_metadata,
        ),
        DaemonLifecycleAuditDefinition(
            event="restart_requested",
            message="daemon restart requested",
        ),
        DaemonLifecycleAuditDefinition(
            event="restart_completed",
            message="daemon restart completed",
            status="ready",
            metadata_validator=_validate_restart_completed_metadata,
        ),
        DaemonLifecycleAuditDefinition(
            event="restart_failed",
            message="daemon restart failed",
            level="error",
            status="error",
            error_policy="required",
            metadata_validator=_validate_restart_failed_metadata,
        ),
    )
)


def write_lifecycle_audit(
    event: DaemonLifecycleAuditEvent,
    *,
    project_root: Path | None,
    error: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> None:
    """Validate and project one non-authoritative lifecycle decision."""

    try:
        definition = DAEMON_LIFECYCLE_AUDIT_REGISTRY.resolve(event)
    except UnknownDefinitionError as exc:
        raise DaemonLifecycleAuditSchemaError(
            f"unknown daemon lifecycle audit event: {event!r}"
        ) from exc
    if metadata is not None and not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
        metadata,
        Mapping,
    ):
        raise DaemonLifecycleAuditSchemaError(
            "lifecycle audit metadata must be a mapping"
        )
    audit_metadata: Mapping[str, object] = {} if metadata is None else metadata
    definition.validate(error=error, metadata=audit_metadata)
    write_observed_log_event(
        "daemon",
        event,
        definition.message,
        project_root=project_root,
        level=definition.level,
        status=definition.status,
        error=error,
        metadata=dict(audit_metadata) or None,
    )
