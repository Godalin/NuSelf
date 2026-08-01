"""Closed audit contracts for daemon socket transport failures."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
    require_exact_metadata,
)
from nuself.runtime.context import runtime_context
from nuself.runtime.observability import report_defined_failure

DaemonTransportAuditEvent = Literal[
    "request_transport_failed",
    "request_failed",
    "response_encode_failed",
    "response_delivery_failed",
]

_MESSAGES: dict[DaemonTransportAuditEvent, str] = {
    "request_transport_failed": "Daemon request transport failed",
    "request_failed": "Daemon request handling failed",
    "response_encode_failed": "Daemon response could not be encoded",
    "response_delivery_failed": "Daemon response could not be delivered",
}


def _require_response_status(metadata: Mapping[str, object]) -> None:
    if metadata["response_status"] not in {"ok", "error"}:
        raise AuditSchemaError(
            "daemon transport response_status is invalid"
        )


def _response_encode(metadata: Mapping[str, object]) -> None:
    require_exact_metadata(
        metadata,
        frozenset({"response_status"}),
        context="daemon transport audit metadata",
    )
    _require_response_status(metadata)


def _response_delivery(metadata: Mapping[str, object]) -> None:
    require_exact_metadata(
        metadata,
        frozenset({"response_status", "fallback"}),
        context="daemon transport audit metadata",
    )
    _require_response_status(metadata)
    if type(metadata["fallback"]) is not bool:
        raise AuditSchemaError(
            "daemon transport fallback must be a boolean"
        )


def _build_registry() -> AuditDefinitionRegistry:
    registry = AuditDefinitionRegistry()
    registry.register(
        AuditEventDefinition(
            component="daemon",
            event="request_transport_failed",
            level="warning",
            status="error",
            error_policy="required",
        )
    )
    registry.register(
        AuditEventDefinition(
            component="daemon",
            event="request_failed",
            level="error",
            status="error",
            error_policy="required",
        )
    )
    registry.register(
        AuditEventDefinition(
            component="daemon",
            event="response_encode_failed",
            level="warning",
            status="error",
            error_policy="required",
            metadata_validator=_response_encode,
        )
    )
    registry.register(
        AuditEventDefinition(
            component="daemon",
            event="response_delivery_failed",
            level="warning",
            status="error",
            error_policy="required",
            metadata_validator=_response_delivery,
        )
    )
    return registry.seal()


DAEMON_TRANSPORT_AUDIT_REGISTRY = _build_registry()


def report_daemon_transport_failure(
    exc: Exception,
    *,
    event: DaemonTransportAuditEvent,
    project_root: Path | None,
    request_id: str | None,
    metadata: dict[str, object] | None = None,
) -> None:
    """Validate and report one daemon socket transport failure."""

    definition = DAEMON_TRANSPORT_AUDIT_REGISTRY.resolve("daemon", event)
    event_metadata = metadata or {}
    context = (
        runtime_context(request_id=request_id, source="daemon")
        if request_id is not None
        else runtime_context(source="daemon")
    )
    with context:
        report_defined_failure(
            exc,
            definition=definition,
            message=_MESSAGES[event],
            project_root=project_root,
            metadata=dict(event_metadata),
        )
