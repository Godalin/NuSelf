"""Closed delivery-audit schemas owned by Notification."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from nuself.runtime.audit.definition import (
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata as _exact,
)
from nuself.runtime.audit.catalog import AuditCatalog

type NotificationAuditEvent = Literal[
    "outbox_delivered",
    "email_dry_run",
    "email_no_config",
    "email_failed",
    "macos_dry_run",
    "macos_unavailable",
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


def _definitions() -> tuple[AuditEventDefinition, ...]:
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
    return definitions

_MESSAGES: dict[NotificationAuditEvent, str] = {
    "outbox_delivered": "Outbox notification delivered",
    "email_dry_run": "Email delivery simulated",
    "email_no_config": "Email delivery skipped without configuration",
    "email_failed": "Email delivery failed",
    "macos_dry_run": "macOS notification delivery simulated",
    "macos_unavailable": "macOS notification delivery unavailable",
    "macos_failed": "macOS notification delivery failed",
}


NOTIFICATION_AUDIT = AuditCatalog[NotificationAuditEvent](
    _definitions(),
    _MESSAGES,
)
