"""Observable boundaries for non-authoritative best-effort side effects."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TypeVar

from nuself.logs import LogComponent, LogLevel, write_log_event
from nuself.runtime.diagnostics import emit_runtime_warning
from nuself.runtime.events import EventPublisher
from nuself.runtime.messages import RuntimeEnvelope

T = TypeVar("T")
DEFAULT_DECODE_ERRORS: tuple[type[Exception], ...] = (
    ValueError,
    KeyError,
    TypeError,
)


def format_exception_chain(exc: BaseException) -> str:
    """Return unique non-empty exception messages from outermost to root cause."""

    messages: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        message = str(current).strip()
        if message and message not in messages:
            messages.append(message)
        if current.__cause__ is not None:
            current = current.__cause__
        elif current.__suppress_context__:
            current = None
        else:
            current = current.__context__
    return " <- ".join(messages) if messages else exc.__class__.__name__


def run_observed_best_effort(
    operation: Callable[[], T],
    *,
    component: LogComponent,
    event: str,
    message: str,
    project_root: Path | None = None,
    metadata: dict[str, object] | None = None,
    errors: tuple[type[Exception], ...] = (Exception,),
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
        )
        return None


def publish_observed_event(
    publisher: EventPublisher,
    *,
    name: str,
    producer: str,
    payload: Mapping[str, object] | None,
    project_root: Path | None,
    failure_component: LogComponent,
    failure_event: str,
    failure_message: str,
    failure_metadata: dict[str, object] | None = None,
) -> RuntimeEnvelope | None:
    """Publish an event without letting subscriber failure alter primary work."""

    return run_observed_best_effort(
        lambda: publisher.publish(
            name=name,
            producer=producer,
            payload=payload,
        ),
        component=failure_component,
        event=failure_event,
        message=failure_message,
        project_root=project_root,
        metadata=failure_metadata,
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

    error = format_exception_chain(exc)
    try:
        write_log_event(
            component,
            event,
            message,
            project_root=project_root,
            level=level,
            status=status,
            error=error,
            metadata=metadata,
        )
    except Exception as log_exc:
        emit_runtime_warning(
            f"{component}/{event}: {error}; structured logging failed: "
            f"{format_exception_chain(log_exc)}",
            stacklevel=3,
        )
