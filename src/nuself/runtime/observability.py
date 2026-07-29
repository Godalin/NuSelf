"""Observable boundaries for non-authoritative best-effort side effects."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypeVar

from nuself.logs import (
    DEFAULT_LOG_RETENTION,
    LogComponent,
    LogEvent,
    LogLevel,
    LogRetentionPolicy,
    create_audit_envelope,
    write_audit_envelope,
    write_log_event,
)
from nuself.runtime.audit_definitions import (
    AuditDefinitionRegistry,
    AuditEventDefinition,
    AuditSchemaError,
)
from nuself.runtime.audit_types import LOG_COMPONENTS
from nuself.runtime.diagnostics import (
    diagnostic_exception_chain,
    diagnostic_exception_message,
    sanitize_diagnostic_metadata,
)
from nuself.runtime.events import EventDeliveryError, EventPublisher
from nuself.runtime.messages import RuntimeEnvelope
from nuself.runtime.warning_definitions import (
    TerminalWarningDefinition,
    TerminalWarningRegistry,
    TerminalWarningSchemaError,
    emit_registered_terminal_warning,
)

T = TypeVar("T")
DEFAULT_DECODE_ERRORS: tuple[type[Exception], ...] = (
    ValueError,
    KeyError,
    TypeError,
)

OBSERVABILITY_PROJECTION_FAILED = "observability_projection_failed"
INTERNAL_EVENT_DELIVERY_FAILED = "internal_event_delivery_failed"
OBSERVABILITY_SINK_FAILED = "runtime/observability_sink_failed"


def _require_exact_metadata(
    metadata: Mapping[str, object],
    expected: frozenset[str],
) -> None:
    actual = frozenset(metadata)
    if actual != expected:
        raise AuditSchemaError(
            "observability metadata fields differ "
            f"(missing={sorted(expected - actual)!r}, "
            f"extra={sorted(actual - expected)!r})"
        )
    for field in expected:
        value = metadata[field]
        if not isinstance(value, str) or not value.strip():
            raise AuditSchemaError(
                f"observability metadata {field} must be a non-blank string"
            )


def _validate_projection_failure(metadata: Mapping[str, object]) -> None:
    _require_exact_metadata(metadata, frozenset({"failed_event"}))


def _validate_delivery_failure(metadata: Mapping[str, object]) -> None:
    _require_exact_metadata(metadata, frozenset({"event", "producer"}))


def _build_observability_failure_registry() -> AuditDefinitionRegistry:
    registry = AuditDefinitionRegistry()
    for component in LOG_COMPONENTS:
        registry.register(
            AuditEventDefinition(
                component=component,
                event=OBSERVABILITY_PROJECTION_FAILED,
                level="warning",
                status="degraded",
                error_policy="required",
                metadata_validator=_validate_projection_failure,
            )
        )
        registry.register(
            AuditEventDefinition(
                component=component,
                event=INTERNAL_EVENT_DELIVERY_FAILED,
                level="warning",
                status="degraded",
                error_policy="required",
                metadata_validator=_validate_delivery_failure,
            )
        )
    return registry.seal()


OBSERVABILITY_FAILURE_REGISTRY = _build_observability_failure_registry()


def _validate_observability_sink_warning(
    metadata: Mapping[str, object],
) -> None:
    if metadata["component"] not in LOG_COMPONENTS:
        raise TerminalWarningSchemaError(
            "observability sink warning component is invalid"
        )
    for field in ("event", "observed_error", "log_error"):
        value = metadata[field]
        if not isinstance(value, str) or not value.strip():
            raise TerminalWarningSchemaError(
                f"observability sink warning {field} must be non-blank"
            )


def _build_observability_terminal_warning_registry(
) -> TerminalWarningRegistry:
    return (
        TerminalWarningRegistry()
        .register(
            TerminalWarningDefinition(
                OBSERVABILITY_SINK_FAILED,
                (
                    "component",
                    "event",
                    "observed_error",
                    "log_error",
                ),
                _validate_observability_sink_warning,
            )
        )
        .seal()
    )


OBSERVABILITY_TERMINAL_WARNING_REGISTRY = (
    _build_observability_terminal_warning_registry()
)


def run_observed_best_effort(
    operation: Callable[[], T],
    *,
    component: LogComponent,
    event: str,
    message: str,
    project_root: Path | None = None,
    metadata: dict[str, object] | None = None,
    errors: tuple[type[Exception], ...] = (Exception,),
    level: LogLevel = "warning",
    status: str = "degraded",
) -> T | None:
    """Run a secondary effect without hiding its failure."""

    try:
        return operation()
    except errors as exc:
        report_observed_failure(
            exc,
            component=component,
            event=event,
            message=message,
            project_root=project_root,
            metadata=metadata,
            level=level,
            status=status,
        )
        return None


def write_observed_log_event(
    component: LogComponent,
    event: str,
    message: str,
    *,
    project_root: Path | None = None,
    level: LogLevel = "info",
    thread_id: str | None = None,
    request_id: str | None = None,
    turn_id: str | None = None,
    job_id: str | None = None,
    trace_id: str | None = None,
    source: str | None = None,
    node: str | None = None,
    duration_ms: int | None = None,
    status: str | None = None,
    error: str | None = None,
    metadata: dict[str, object] | None = None,
    retention_policy: LogRetentionPolicy = DEFAULT_LOG_RETENTION,
) -> LogEvent | None:
    """Write one auxiliary log without changing its owning operation."""

    envelope = create_audit_envelope(
        component,
        event,
        message,
        level=level,
        thread_id=thread_id,
        request_id=request_id,
        turn_id=turn_id,
        job_id=job_id,
        trace_id=trace_id,
        source=source,
        node=node,
        duration_ms=duration_ms,
        status=status,
        error=error,
        metadata=metadata,
    )
    try:
        return write_audit_envelope(
            envelope,
            project_root=project_root,
            retention_policy=retention_policy,
        )
    except Exception as exc:  # noqa: BLE001 - auxiliary sink is non-authoritative
        report_observability_projection_failure(
            exc,
            component=component,
            failed_event=event,
            project_root=project_root,
        )
        return None


def report_observability_projection_failure(
    exc: Exception,
    *,
    component: LogComponent,
    failed_event: str,
    project_root: Path | None,
) -> None:
    """Report one failed secondary log projection through a fixed contract."""

    metadata: dict[str, object] = {"failed_event": failed_event}
    definition = OBSERVABILITY_FAILURE_REGISTRY.resolve(
        component=component,
        event=OBSERVABILITY_PROJECTION_FAILED,
    )
    error = diagnostic_exception_chain(exc)
    definition.validate(
        level=definition.level,
        status=definition.status,
        error=error,
        metadata=metadata,
    )
    report_observed_failure(
        exc,
        component=component,
        event=OBSERVABILITY_PROJECTION_FAILED,
        message="Secondary observability projection failed",
        project_root=project_root,
        metadata=metadata,
        level=definition.level,
        status=definition.status or "degraded",
    )


def publish_observed_event(
    publisher: EventPublisher,
    *,
    name: str,
    producer: str,
    payload: Mapping[str, object] | None,
    project_root: Path | None,
    failure_component: LogComponent,
) -> RuntimeEnvelope:
    """Publish an event without letting projection failure alter primary work."""

    try:
        return publisher.publish(
            name=name,
            producer=producer,
            payload=payload,
        )
    except EventDeliveryError as exc:
        report_internal_event_delivery_failure(
            exc,
            component=failure_component,
            project_root=project_root,
        )
        return exc.event


def report_internal_event_delivery_failure(
    exc: EventDeliveryError,
    *,
    component: LogComponent,
    project_root: Path | None,
) -> None:
    """Report projection delivery failure from its immutable envelope."""

    metadata: dict[str, object] = {
        "event": exc.event.name,
        "producer": exc.event.producer,
    }
    definition = OBSERVABILITY_FAILURE_REGISTRY.resolve(
        component,
        INTERNAL_EVENT_DELIVERY_FAILED,
    )
    error = diagnostic_exception_chain(exc)
    definition.validate(
        level=definition.level,
        status=definition.status,
        error=error,
        metadata=metadata,
    )
    report_observed_failure(
        exc,
        component=component,
        event=INTERNAL_EVENT_DELIVERY_FAILED,
        message="Internal event delivery failed",
        project_root=project_root,
        metadata=metadata,
        level=definition.level,
        status=definition.status or "degraded",
    )


def decode_observed_record(
    wire: Mapping[str, object],
    decoder: Callable[[dict[str, object]], T],
    *,
    component: LogComponent,
    collection: str,
    project_root: Path | None = None,
    errors: tuple[type[Exception], ...] = DEFAULT_DECODE_ERRORS,
) -> T | None:
    """Decode one stored record while isolating declared schema failures."""

    record = dict(wire)
    try:
        return decoder(record)
    except errors as exc:
        raw_id = record.get("id")
        record_id = raw_id if isinstance(raw_id, str) and raw_id else "<unknown>"
        report_corrupt_record(
            exc,
            component=component,
            collection=collection,
            record_id=record_id,
            project_root=project_root,
        )
        return None


def report_corrupt_record(
    exc: Exception,
    *,
    component: LogComponent,
    collection: str,
    record_id: str,
    project_root: Path | None = None,
) -> None:
    """Report one isolated corrupt record without exposing its payload."""

    report_observed_failure(
        exc,
        component=component,
        event="record_decode_failed",
        message=f"Skipped malformed record in {collection}",
        project_root=project_root,
        metadata={"collection": collection, "record_id": record_id},
    )


def report_observed_failure(
    exc: Exception,
    *,
    component: LogComponent,
    event: str,
    message: str,
    project_root: Path | None,
    metadata: dict[str, object] | None,
    level: LogLevel = "warning",
    status: str = "degraded",
) -> None:
    """Report an already-caught failure without replacing that failure."""

    error = diagnostic_exception_chain(exc)
    try:
        write_log_event(
            component,
            event,
            message,
            project_root=project_root,
            level=level,
            status=status,
            error=error,
            metadata=sanitize_diagnostic_metadata(metadata),
        )
    except Exception as log_exc:
        emit_registered_terminal_warning(
            OBSERVABILITY_TERMINAL_WARNING_REGISTRY,
            OBSERVABILITY_SINK_FAILED,
            {
                "component": component,
                "event": event,
                "observed_error": error,
                "log_error": diagnostic_exception_message(log_exc),
            },
            stacklevel=3,
        )
