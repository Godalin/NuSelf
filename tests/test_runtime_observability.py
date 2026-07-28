from pathlib import Path

import pytest

from nuself.logs import read_log_events
from nuself.runtime.observability import (
    format_exception_chain,
    run_observed_best_effort,
)


def test_format_exception_chain_preserves_unique_cause_messages() -> None:
    try:
        try:
            raise ValueError("root")
        except ValueError as exc:
            raise RuntimeError("outer") from exc
    except RuntimeError as exc:
        assert format_exception_chain(exc) == "outer <- root"


def test_best_effort_returns_none_and_writes_structured_failure(
    tmp_path: Path,
) -> None:
    def fail() -> None:
        raise RuntimeError("trace unavailable")

    result = run_observed_best_effort(
        fail,
        component="memory",
        event="trace_recording_failed",
        message="Could not record trace",
        project_root=tmp_path,
        metadata={"memory_id": "m1"},
    )

    assert result is None
    event = read_log_events(project_root=tmp_path, component="memory")[-1]
    assert event.event == "trace_recording_failed"
    assert event.level == "warning"
    assert event.status == "degraded"
    assert event.error == "trace unavailable"
    assert event.metadata == {"memory_id": "m1"}


def test_best_effort_warns_when_structured_sink_also_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="memory/trace_recording_failed.*primary failed.*disk full",
    ):
        result = run_observed_best_effort(
            lambda: (_ for _ in ()).throw(RuntimeError("primary failed")),
            component="memory",
            event="trace_recording_failed",
            message="Could not record trace",
        )

    assert result is None
