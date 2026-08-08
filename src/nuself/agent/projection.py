"""Canonical runtime-event projection of framework Tool outcomes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from nuself.agent.outcome import ToolOutcome
from nuself.log.record import LogEvent
from nuself.runtime.audit.types import LogComponent
from nuself.runtime.messages import thaw_json_value
from nuself.runtime.observability import report_observed_failure
from nuself.runtime.observability import (
    run_observed_best_effort,
    write_observed_log_event,
)

SERVICE_TOOL_EVENT = "service_tool_called"
SERVICE_TOOL_MESSAGE = "Service tool outcome recorded"


def tool_outcome_fields(
    outcome: ToolOutcome,
    *,
    service_component: str,
) -> tuple[str, dict[str, object]]:
    """Return the canonical status and metadata for one Tool outcome."""

    if not service_component.strip():
        raise ValueError("Tool service component must not be blank")
    metadata: dict[str, object] = {
        "service_component": service_component,
        "tool": outcome.name,
        "args": thaw_json_value(outcome.args),
    }
    if outcome.error is not None:
        metadata["error"] = outcome.error
    else:
        metadata["result"] = cast(str, outcome.result)
    return ("completed" if outcome.succeeded else "failed"), metadata


def tool_outcome_snapshot(
    producer: LogComponent,
    outcome: ToolOutcome,
    *,
    service_component: str,
) -> dict[str, object]:
    """Return the canonical timestamp-free persisted outcome shape."""

    status, metadata = tool_outcome_fields(
        outcome,
        service_component=service_component,
    )
    snapshot: dict[str, object] = {
        "component": producer,
        "event": SERVICE_TOOL_EVENT,
        "message": SERVICE_TOOL_MESSAGE,
        "status": status,
        "metadata": metadata,
    }
    if outcome.error is not None:
        snapshot["error"] = outcome.error
    return snapshot


@dataclass(frozen=True)
class LogToolOutcomeProjection:
    """Write one canonical structured outcome through the audit log."""

    component: LogComponent
    project_root: Path | None
    activity_sink: Callable[[LogEvent], None] | None = None

    def project_best_effort(
        self,
        outcome: ToolOutcome,
        *,
        service_component: str,
    ) -> None:
        try:
            status, metadata = tool_outcome_fields(
                outcome,
                service_component=service_component,
            )
        except Exception as error:
            self.report_capture_failure(error, tool=outcome.name)
            return
        event = write_observed_log_event(
            self.component,
            SERVICE_TOOL_EVENT,
            SERVICE_TOOL_MESSAGE,
            project_root=self.project_root,
            status=status,
            error=outcome.error,
            metadata=metadata,
        )
        activity_sink = self.activity_sink
        if event is not None and activity_sink is not None:
            run_observed_best_effort(
                lambda: activity_sink(event),
                component=self.component,
                event="tool_outcome_live_projection_failed",
                message="Could not deliver live service Tool outcome",
                project_root=self.project_root,
                metadata={"tool": outcome.name},
            )

    def report_capture_failure(
        self,
        error: Exception,
        *,
        tool: str,
    ) -> None:
        report_observed_failure(
            error,
            component=self.component,
            event="tool_outcome_capture_failed",
            message="Could not capture service Tool outcome",
            project_root=self.project_root,
            metadata={"tool": tool},
        )


__all__ = [
    "LogToolOutcomeProjection",
    "tool_outcome_fields",
    "tool_outcome_snapshot",
]
