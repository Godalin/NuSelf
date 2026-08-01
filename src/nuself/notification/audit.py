"""Closed delivery-audit schemas owned by Notification."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from nuself.logs import LogEvent, write_log_event
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata as _exact,
)
from nuself.runtime.observability import (
    report_defined_failure,
)

NotificationAuditEvent = Literal[
    "outbox_delivered",
    "email_dry_run",
    "email_no_config",
    "email_failed",
    "macos_dry_run",
    "macos_unavailable",
    "macos_failed",
]
NotificationSuccessEvent = Literal[
    "outbox_delivered",
    "email_dry_run",
    "macos_dry_run",
    "macos_unavailable",
]
NotificationFailureEvent = Literal[
    "email_no_config",
    "email_failed",
    "macos_failed",
]

def _string(metadata: Mapping[str, object], field: str) -> str:
    value = metadata[field]
    if not isinstance(value, str) or not value:
        raise AuditSchemaError(f"audit metadata {field!r} must be non-empty")
    return value


def _entry_attempt(metadata: Mapping[str, object]) -> None:
    _exact(metadata, frozenset({"entry_id", "attempt"}))
    _string(metadata, "entry_id")
    attempt = metadata["attempt"]
    if type(attempt) is not int or attempt < 0:
        raise AuditSchemaError(
            "audit metadata 'attempt' must be a non-negative integer"
        )


def _build_registry() -> AuditDefinitionRegistry:
    definitions = (
        AuditEventDefinition(
            "outbox", "outbox_delivered", "info", "delivered",
            metadata_validator=_entry_attempt,
        ),
        AuditEventDefinition(
            "outbox", "email_dry_run", "debug", "simulated",
            metadata_validator=_entry_attempt,
        ),
        AuditEventDefinition(
            "outbox", "email_no_config", "warning", "failed",
            error_policy="required",
            metadata_validator=_entry_attempt,
        ),
        AuditEventDefinition(
            "outbox", "email_failed", "warning", "failed",
            error_policy="required",
            metadata_validator=_entry_attempt,
        ),
        AuditEventDefinition(
            "outbox", "macos_dry_run", "debug", "simulated",
            metadata_validator=_entry_attempt,
        ),
        AuditEventDefinition(
            "outbox", "macos_unavailable", "info", "unavailable",
            metadata_validator=_entry_attempt,
        ),
        AuditEventDefinition(
            "outbox", "macos_failed", "warning", "failed",
            error_policy="required",
            metadata_validator=_entry_attempt,
        ),
    )
    registry = AuditDefinitionRegistry()
    for definition in definitions:
        registry.register(definition)
    return registry.seal()


NOTIFICATION_AUDIT_REGISTRY = _build_registry()

_MESSAGES: dict[NotificationAuditEvent, str] = {
    "outbox_delivered": "Outbox notification delivered",
    "email_dry_run": "Email delivery simulated",
    "email_no_config": "Email delivery skipped without configuration",
    "email_failed": "Email delivery failed",
    "macos_dry_run": "macOS notification delivery simulated",
    "macos_unavailable": "macOS notification delivery unavailable",
    "macos_failed": "macOS notification delivery failed",
}


def write_notification_audit(
    event: NotificationSuccessEvent,
    *,
    project_root: Path | None,
    metadata: dict[str, object],
) -> LogEvent:
    """Validate and write one delivery-channel audit.

    These records are the observable output of log-only/dry-run adapters, so a
    sink failure remains an adapter failure rather than being hidden.
    """

    definition = NOTIFICATION_AUDIT_REGISTRY.resolve("outbox", event)
    definition.validate(
        level=definition.level,
        status=definition.status,
        error=None,
        metadata=metadata,
    )
    return write_log_event(
        definition.component,
        definition.event,
        _MESSAGES[event],
        project_root=project_root,
        level=definition.level,
        status=definition.status,
        metadata=dict(metadata),
    )


def report_notification_failure(
    exc: Exception,
    *,
    event: NotificationFailureEvent,
    project_root: Path | None,
    metadata: dict[str, object],
) -> None:
    """Validate and report one caught Notification failure."""

    definition = NOTIFICATION_AUDIT_REGISTRY.resolve("outbox", event)
    report_defined_failure(
        exc,
        definition=definition,
        message=_MESSAGES[event],
        project_root=project_root,
        metadata=dict(metadata),
    )
