"""Closed audit contracts for daemon request decisions."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from nuself.log.record import LogEvent
from nuself.runtime.audit.definition import (
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata,
)
from nuself.runtime.audit.catalog import AuditCatalog
from nuself.runtime.context import runtime_context

type DaemonRequestAuditEvent = Literal[
    "request_rejected",
    "chat_turn_failed",
    "chat_turn_completed",
    "shutdown_requested",
]
type DaemonRequestFailureEvent = Literal[
    "request_rejected",
    "chat_turn_failed",
]
type DaemonRequestSuccessEvent = Literal[
    "chat_turn_completed",
    "shutdown_requested",
]

_MESSAGES: dict[DaemonRequestAuditEvent, str] = {
    "request_rejected": "Daemon request payload rejected",
    "chat_turn_failed": "Daemon chat turn failed",
    "chat_turn_completed": "Daemon chat turn completed",
    "shutdown_requested": "Daemon shutdown requested",
}


def _request_rejected(metadata: Mapping[str, object]) -> None:
    require_exact_metadata(
        metadata,
        frozenset({"request_type"}),
        context="daemon request audit metadata",
    )
    value = metadata["request_type"]
    if not isinstance(value, str) or not value.strip():
        raise AuditSchemaError(
            "daemon request audit request_type must be a non-blank string"
        )


def _chat_completed(metadata: Mapping[str, object]) -> None:
    require_exact_metadata(
        metadata,
        frozenset({"evidence_references"}),
        context="daemon request audit metadata",
    )
    evidence_references = metadata["evidence_references"]
    if type(evidence_references) is not int or evidence_references < 0:
        raise AuditSchemaError(
            "daemon request audit evidence_references must be non-negative"
        )


def _definitions() -> tuple[AuditEventDefinition, ...]:
    return (
        AuditEventDefinition(
            component="daemon",
            event="request_rejected",
            level="warning",
            status="error",
            error_policy="required",
            metadata_validator=_request_rejected,
        ),
        AuditEventDefinition(
            component="daemon",
            event="chat_turn_failed",
            level="error",
            status="error",
            error_policy="required",
        ),
        AuditEventDefinition(
            component="daemon",
            event="chat_turn_completed",
            level="info",
            status="ok",
            duration_policy="required",
            metadata_validator=_chat_completed,
        ),
        AuditEventDefinition(
            component="daemon",
            event="shutdown_requested",
            level="info",
            status="accepted",
        ),
    )


DAEMON_REQUEST_AUDIT = AuditCatalog[DaemonRequestAuditEvent](
    _definitions(),
    _MESSAGES,
)


def write_daemon_request_audit(
    event: DaemonRequestSuccessEvent,
    *,
    project_root: Path,
    request_id: str,
    duration_ms: int | None = None,
    metadata: dict[str, object] | None = None,
) -> LogEvent | None:
    """Validate and write one successful daemon request decision."""

    return DAEMON_REQUEST_AUDIT.write(
        event,
        project_root=project_root,
        request_id=request_id,
        duration_ms=duration_ms,
        metadata=metadata,
    )


def report_daemon_request_failure(
    exc: Exception,
    *,
    event: DaemonRequestFailureEvent,
    project_root: Path,
    request_id: str,
    metadata: dict[str, object] | None = None,
) -> None:
    """Validate and report one failed daemon request decision."""

    with runtime_context(request_id=request_id):
        DAEMON_REQUEST_AUDIT.failure(
            exc,
            event=event,
            project_root=project_root,
            metadata=metadata,
        )
