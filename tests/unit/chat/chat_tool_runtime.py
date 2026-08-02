from __future__ import annotations

# pyright: reportPrivateUsage=false

from pathlib import Path

from nuself.agent.chat.tool_runtime import ConversationToolRuntime
from nuself.log.reader import read_log_events


def test_tool_log_failure_reporter_writes_structured_degradation(
    tmp_path: Path,
) -> None:
    runtime = object.__new__(ConversationToolRuntime)
    runtime._project_root = tmp_path

    runtime.report_log_failure(OSError("audit unavailable"))

    [event] = read_log_events(project_root=tmp_path, component="chat")
    assert event.event == "observability_projection_failed"
    assert event.status == "degraded"
    assert event.error == "audit unavailable"
    assert event.metadata == {"failed_event": "service_tool_called"}
