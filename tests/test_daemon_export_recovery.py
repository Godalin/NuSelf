import json
import threading
from pathlib import Path
import time

import pytest

from nuself.daemon.reason_export import (
    inspect_export_job,
    persist_export_failure,
)
from nuself.daemon.server import DaemonState
from nuself.logs import LogEvent, read_log_events
from nuself.reason.output import (
    ReasonOutputManifest,
    ReasonOutputProgress,
    ReasonOutputService,
)
from nuself.storage import write_json_atomic
from nuself.runtime.jobs import JobMessage
from nuself.runtime.context import runtime_context
from nuself.workspace import PrivateWorkspaceStore


def _manifest(
    *,
    job_id: str = "job_1",
    thread_id: str = "thread_1",
    status: str = "planned",
    attempts: int = 0,
) -> ReasonOutputManifest:
    return ReasonOutputManifest(
        job_id=job_id,
        thread_id=thread_id,
        mode="report",
        output_format="markdown",
        source_start_index=0,
        source_end_index=None,
        source_step_ids=(),
        segment_size=1,
        status=status,
        attempts=attempts,
    )


def _job_paths(
    root: Path,
    *,
    job_id: str = "job_1",
    thread_id: str = "thread_1",
) -> tuple[Path, Path]:
    job_root = (
        PrivateWorkspaceStore(root, scope="reason").paths(thread_id).artifacts
        / "export"
        / "jobs"
        / job_id
    )
    job_root.mkdir(parents=True, exist_ok=True)
    return job_root / "manifest.json", job_root / "progress.json"


def _progress(
    *,
    job_id: str = "job_1",
    thread_id: str = "thread_1",
) -> ReasonOutputProgress:
    return ReasonOutputProgress(
        job_id=job_id,
        thread_id=thread_id,
        status="planned",
        completed_chunks=(),
        total_chunks=1,
        pdf_status="pending",
        pdf_path=None,
        updated_at="2026-01-01T00:00:00+00:00",
    )


def _wait_for_event(root: Path, event_name: str) -> LogEvent:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        events = read_log_events(project_root=root, component="daemon")
        for event in events:
            if event.event == event_name:
                return event
        time.sleep(0.01)
    raise AssertionError(f"timed out waiting for {event_name}")


def test_inspection_marks_completed_manifest_terminal(tmp_path: Path) -> None:
    manifest_path, _ = _job_paths(tmp_path)
    write_json_atomic(
        manifest_path,
        _manifest(status="complete").to_wire(),
    )

    inspection = inspect_export_job(
        manifest_path,
        job_id="job_1",
        thread_id="thread_1",
    )

    assert inspection.terminal is True


def test_inspection_keeps_valid_manifest_when_progress_is_corrupt(
    tmp_path: Path,
) -> None:
    manifest_path, progress_path = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest().to_wire())
    progress_path.write_text("{", encoding="utf-8")

    inspection = inspect_export_job(
        manifest_path,
        job_id="job_1",
        thread_id="thread_1",
    )

    assert inspection.terminal is False
    assert inspection.total_chunks == "?"
    assert isinstance(inspection.progress_error, json.JSONDecodeError)


def test_inspection_treats_missing_progress_as_normal(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest().to_wire())

    inspection = inspect_export_job(
        manifest_path,
        job_id="job_1",
        thread_id="thread_1",
    )

    assert inspection.total_chunks == "?"
    assert inspection.progress_error is None


def test_inspection_retains_progress_io_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, progress_path = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest().to_wire())
    write_json_atomic(progress_path, _progress().to_wire())
    original_read_text = Path.read_text

    def fail_progress_read(
        path: Path,
        encoding: str | None = None,
        errors: str | None = None,
    ) -> str:
        if path == progress_path:
            raise PermissionError("progress permission denied")
        return original_read_text(
            path,
            encoding=encoding,
            errors=errors,
        )

    monkeypatch.setattr(Path, "read_text", fail_progress_read)

    inspection = inspect_export_job(
        manifest_path,
        job_id="job_1",
        thread_id="thread_1",
    )

    assert inspection.total_chunks == "?"
    assert isinstance(inspection.progress_error, PermissionError)


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("status", ""),
        ("completed_chunks", [0.0]),
        ("completed_chunks", [0, 0]),
        ("completed_chunks", [-1]),
        ("completed_chunks", [1]),
        ("total_chunks", True),
        ("pdf_status", "unknown"),
        ("updated_at", "2026-01-01T00:00:00"),
    ),
)
def test_progress_from_wire_rejects_invalid_fields(
    field_name: str,
    value: object,
) -> None:
    wire = _progress().to_wire()
    wire[field_name] = value

    with pytest.raises(ValueError):
        ReasonOutputProgress.from_wire(wire)


def test_progress_from_wire_rejects_shape_drift() -> None:
    wire = _progress().to_wire()
    del wire["pdf_path"]
    wire["unexpected"] = True

    with pytest.raises(
        ValueError,
        match="missing=.*pdf_path.*unknown=.*unexpected",
    ):
        ReasonOutputProgress.from_wire(wire)


def test_persist_export_failure_updates_attempt_state(tmp_path: Path) -> None:
    manifest_path, _ = _job_paths(tmp_path)
    write_json_atomic(
        manifest_path,
        _manifest(attempts=4).to_wire(),
    )

    updated = persist_export_failure(
        manifest_path,
        RuntimeError("compose failed"),
        max_attempts=5,
    )

    assert updated.status == "failed"
    assert updated.attempts == 5
    assert updated.last_error == "compose failed"
    persisted = ReasonOutputManifest.from_wire(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    assert persisted == updated


def test_worker_does_not_compose_corrupt_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, _ = _job_paths(tmp_path)
    manifest_path.write_text("{", encoding="utf-8")
    calls: list[str] = []

    def compose(
        self: ReasonOutputService,
        thread_id: str,
        job_id: str,
        runner: object,
    ) -> ReasonOutputManifest:
        calls.append(job_id)
        return _manifest(job_id=job_id, thread_id=thread_id)

    monkeypatch.setattr(ReasonOutputService, "compose_with_runner", compose)
    state = DaemonState(tmp_path)
    with runtime_context(
        request_id="request-1",
        turn_id="turn-1",
        trace_id="trace-1",
        source="daemon",
    ):
        state.reason_export_worker.enqueue(
            JobMessage.create(
                name="reason.output.export",
                producer="test",
                job_id="job_1",
                resource_id="thread_1",
            )
        )
    state.start_background_export_worker()
    event = _wait_for_event(tmp_path, "export_job_manifest_invalid")
    state.shutdown_requested.set()
    state.stop_background_export_worker()

    assert calls == []
    assert event.request_id == "request-1"
    assert event.turn_id == "turn-1"
    assert event.trace_id == "trace-1"
    assert event.job_id == "job_1"
    assert event.thread_id == "thread_1"
    assert event.source == "daemon.worker.export_worker"
    assert event.metadata == {"job_id": "job_1", "thread_id": "thread_1"}


def test_worker_reports_invalid_progress_and_continues(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, progress_path = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest().to_wire())
    progress_path.write_text(
        '{"private":"secret progress"',
        encoding="utf-8",
    )
    calls: list[str] = []

    def compose(
        self: ReasonOutputService,
        thread_id: str,
        job_id: str,
        runner: object,
    ) -> ReasonOutputManifest:
        calls.append(job_id)
        return _manifest(job_id=job_id, thread_id=thread_id)

    monkeypatch.setattr(ReasonOutputService, "compose_with_runner", compose)
    state = DaemonState(tmp_path)
    state.reason_export_worker.enqueue(
        JobMessage.create(
            name="reason.output.export",
            producer="test",
            job_id="job_1",
            resource_id="thread_1",
        )
    )
    state.start_background_export_worker()
    event = _wait_for_event(tmp_path, "export_job_progress_invalid")
    state.shutdown_requested.set()
    state.stop_background_export_worker()

    assert calls
    assert set(calls) == {"job_1"}
    assert event.status == "degraded"
    assert event.metadata == {
        "job_id": "job_1",
        "thread_id": "thread_1",
    }
    assert "secret progress" not in str(event.to_record())


def test_worker_retry_message_inherits_job_correlation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, progress_path = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest().to_wire())
    write_json_atomic(progress_path, _progress().to_wire())
    captured: list[JobMessage] = []

    def compose(
        self: ReasonOutputService,
        thread_id: str,
        job_id: str,
        runner: object,
    ) -> ReasonOutputManifest:
        raise RuntimeError("compose failed")

    class FakeTimer:
        def __init__(
            self,
            interval: float,
            function: object,
            args: tuple[JobMessage, ...],
        ) -> None:
            del interval, function
            captured.extend(args)

        def start(self) -> None:
            return None

        def cancel(self) -> None:
            return None

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(ReasonOutputService, "compose_with_runner", compose)
    monkeypatch.setattr(
        "nuself.daemon.reason_export.threading.Timer",
        FakeTimer,
    )

    def no_owners(self: PrivateWorkspaceStore) -> list[str]:
        del self
        return []

    monkeypatch.setattr(
        PrivateWorkspaceStore,
        "list_owners",
        no_owners,
    )
    state = DaemonState(tmp_path)
    with runtime_context(
        request_id="request-retry",
        turn_id="turn-retry",
        trace_id="trace-retry",
        source="daemon",
    ):
        state.reason_export_worker.enqueue(
            JobMessage.create(
                name="reason.output.export",
                producer="test",
                job_id="job_1",
                resource_id="thread_1",
            )
        )

    state.start_background_export_worker()
    event = _wait_for_event(tmp_path, "export_job_retry")
    state.shutdown_requested.set()
    state.stop_background_export_worker()

    assert event.request_id == "request-retry"
    assert event.job_id == "job_1"
    assert event.thread_id == "thread_1"
    assert len(captured) == 1
    retry = captured[0]
    assert retry.envelope.context.request_id == "request-retry"
    assert retry.envelope.context.turn_id == "turn-retry"
    assert retry.envelope.context.trace_id == "trace-retry"
    assert retry.envelope.context.job_id == "job_1"
    assert retry.envelope.context.thread_id == "thread_1"
    assert retry.envelope.context.source == "daemon.worker.export_worker"


def test_worker_stop_closes_retry_scheduling_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, progress_path = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest().to_wire())
    write_json_atomic(progress_path, _progress().to_wire())
    compose_started = threading.Event()
    release_compose = threading.Event()
    scheduled: list[JobMessage] = []

    def compose(
        self: ReasonOutputService,
        thread_id: str,
        job_id: str,
        runner: object,
    ) -> ReasonOutputManifest:
        del self, thread_id, job_id, runner
        compose_started.set()
        assert release_compose.wait(1)
        raise RuntimeError("compose failed during shutdown")

    class FakeTimer:
        def __init__(
            self,
            interval: float,
            function: object,
            args: tuple[JobMessage, ...],
        ) -> None:
            del interval, function
            scheduled.extend(args)

        def start(self) -> None:
            return None

        def cancel(self) -> None:
            return None

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(ReasonOutputService, "compose_with_runner", compose)
    monkeypatch.setattr(
        "nuself.daemon.reason_export.threading.Timer",
        FakeTimer,
    )
    state = DaemonState(tmp_path)
    state.start_background_export_worker()
    assert compose_started.wait(1)

    state.shutdown_requested.set()
    state.reason_export_worker.stop()
    release_compose.set()
    state.stop_background_export_worker()

    assert scheduled == []
    assert state.reason_export_worker.pending_retry_count == 0


def test_worker_logs_state_persistence_failure_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, progress_path = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest().to_wire())
    write_json_atomic(
        progress_path,
        _progress().to_wire(),
    )

    def compose(
        self: ReasonOutputService,
        thread_id: str,
        job_id: str,
        runner: object,
    ) -> ReasonOutputManifest:
        raise RuntimeError("compose failed")

    def fail_persist(*args: object, **kwargs: object) -> ReasonOutputManifest:
        raise OSError("disk full")

    monkeypatch.setattr(ReasonOutputService, "compose_with_runner", compose)
    monkeypatch.setattr(
        "nuself.daemon.reason_export.persist_export_failure",
        fail_persist,
    )
    state = DaemonState(tmp_path)
    state.start_background_export_worker()
    event = _wait_for_event(tmp_path, "export_job_state_persist_failed")
    state.shutdown_requested.set()
    state.stop_background_export_worker()

    assert event.error == "disk full <- compose failed"
    assert event.metadata == {
        "job_id": "job_1",
        "thread_id": "thread_1",
        "operation_error": "compose failed",
    }
    assert state.reason_export_worker.pending_retry_count == 0
