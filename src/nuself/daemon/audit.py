"""Observable projections of authoritative daemon lifecycle decisions."""

from __future__ import annotations

from pathlib import Path

from nuself.logs import LogLevel
from nuself.runtime.observability import write_observed_log_event


def write_lifecycle_audit(
    event: str,
    message: str,
    *,
    project_root: Path | None,
    level: LogLevel = "info",
    status: str | None = None,
    error: str | None = None,
    metadata: dict[str, object] | None = None,
) -> None:
    """Project a lifecycle decision without changing its authoritative result."""

    write_observed_log_event(
        "daemon",
        event,
        message,
        project_root=project_root,
        level=level,
        status=status,
        error=error,
        metadata=metadata,
        failure_event="lifecycle_audit_write_failed",
        failure_message=f"Could not record daemon lifecycle audit event {event}",
    )
