from pathlib import Path

import pytest

from nuself.agent.middleware import ToolOutcome
from nuself.agent.tool_audit import (
    SERVICE_TOOL_MESSAGE,
    ToolOutcomeProjection,
)
from nuself.log.reader import read_log_events


def test_success_projection_owns_live_and_snapshot_shape(
    tmp_path: Path,
) -> None:
    projection = ToolOutcomeProjection(
        component="chat",
        service_component="memory",
        outcome=ToolOutcome(
            "memory_archive",
            {"entry_id": "m1"},
            result="archived",
        ),
    )

    event = projection.write(project_root=tmp_path)
    snapshot = projection.to_snapshot()

    assert event.message == SERVICE_TOOL_MESSAGE
    assert event.status == "completed"
    assert event.error is None
    assert dict(event.metadata or {}) == snapshot["metadata"]
    assert snapshot == {
        "component": "chat",
        "event": "service_tool_called",
        "message": SERVICE_TOOL_MESSAGE,
        "status": "completed",
        "metadata": {
            "service_component": "memory",
            "tool": "memory_archive",
            "args": {"entry_id": "m1"},
            "result": "archived",
        },
    }


def test_failure_projection_repeats_canonical_error(
    tmp_path: Path,
) -> None:
    projection = ToolOutcomeProjection(
        component="reasoning",
        service_component="workspace",
        outcome=ToolOutcome(
            "workspace_put",
            {"key": "draft"},
            error="storage unavailable",
        ),
    )

    projection.write_observed(project_root=tmp_path)
    event = read_log_events(
        project_root=tmp_path,
        component="reasoning",
    )[-1]

    assert event.status == "failed"
    assert event.error == "storage unavailable"
    assert event.metadata is not None
    assert event.metadata["error"] == event.error
    assert projection.to_snapshot()["error"] == event.error


@pytest.mark.parametrize(
    ("name", "result", "error"),
    [
        ("", "ok", None),
        ("tool", "", None),
        ("tool", None, ""),
    ],
)
def test_tool_outcome_rejects_blank_contract_fields(
    name: str,
    result: str | None,
    error: str | None,
) -> None:
    with pytest.raises(ValueError):
        ToolOutcome(name=name, args={}, result=result, error=error)


def test_projection_rejects_blank_service_component() -> None:
    with pytest.raises(ValueError, match="service component"):
        ToolOutcomeProjection(
            component="chat",
            service_component=" ",
            outcome=ToolOutcome("tool", {}, result="ok"),
        )
