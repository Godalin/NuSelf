"""Observable projections of authoritative daemon lifecycle decisions."""

from __future__ import annotations

from pathlib import Path

from nuself.logs import LogLevel, write_log_event
from nuself.runtime.observability import run_observed_best_effort


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

    run_observed_best_effort(
        lambda: write_log_event(
            "daemon",
            event,
            message,
            project_root=project_root,
            level=level,
            status=status,
            error=error,
            metadata=metadata,
        ),
        component="daemon",
        event="lifecycle_audit_write_failed",
        message=f"Could not record daemon lifecycle audit event {event}",
        project_root=project_root,
        metadata={"audit_event": event},
    )
