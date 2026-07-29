"""Canonical projection of framework tool outcomes into audit records."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from nuself.agent.middleware import ToolOutcome
from nuself.logs import LogComponent, LogEvent, write_log_event
from nuself.runtime.messages import thaw_json_value
from nuself.runtime.observability import write_observed_log_event

SERVICE_TOOL_EVENT = "service_tool_called"
SERVICE_TOOL_MESSAGE = "Service tool outcome recorded"


@dataclass(frozen=True)
class ToolOutcomeProjection:
    """One validated service-tool outcome ready for every audit sink."""

    component: LogComponent
    service_component: str
    outcome: ToolOutcome

    def __post_init__(self) -> None:
        if not self.service_component.strip():
            raise ValueError("tool service component must not be blank")

    @property
    def status(self) -> str:
        return "failed" if self.outcome.error is not None else "completed"

    @property
    def metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "service_component": self.service_component,
            "tool": self.outcome.name,
            "args": thaw_json_value(self.outcome.args),
        }
        if self.outcome.error is not None:
            metadata["error"] = self.outcome.error
        else:
            metadata["result"] = cast(str, self.outcome.result)
        return metadata

    def write(self, *, project_root: Path | None) -> LogEvent:
        """Write the canonical event, allowing the owner to observe failure."""

        return write_log_event(
            self.component,
            SERVICE_TOOL_EVENT,
            SERVICE_TOOL_MESSAGE,
            project_root=project_root,
            status=self.status,
            error=self.outcome.error,
            metadata=self.metadata,
        )

    def write_observed(self, *, project_root: Path | None) -> LogEvent | None:
        """Write without allowing this secondary projection to alter work."""

        return write_observed_log_event(
            self.component,
            SERVICE_TOOL_EVENT,
            SERVICE_TOOL_MESSAGE,
            project_root=project_root,
            status=self.status,
            error=self.outcome.error,
            metadata=self.metadata,
            failure_event="tool_log_projection_failed",
            failure_message="Could not project service tool outcome",
            failure_metadata={"tool": self.outcome.name},
        )

    def to_snapshot(self) -> dict[str, object]:
        """Return the exact timestamp-free shape persisted by domain records."""

        snapshot: dict[str, object] = {
            "component": self.component,
            "event": SERVICE_TOOL_EVENT,
            "message": SERVICE_TOOL_MESSAGE,
            "status": self.status,
            "metadata": self.metadata,
        }
        if self.outcome.error is not None:
            snapshot["error"] = self.outcome.error
        return snapshot
