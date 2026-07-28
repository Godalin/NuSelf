import json
from pathlib import Path
import time

import pytest

from nuself.daemon.server import (
    DaemonState,
    _inspect_export_job,  # pyright: ignore[reportPrivateUsage]
    _persist_export_failure,  # pyright: ignore[reportPrivateUsage]
)
from nuself.logs import LogEvent, read_log_events
from nuself.reason.output import (
    ReasonOutputManifest,
    ReasonOutputProgress,
    ReasonOutputService,
    write_json_atomic,
)
from nuself.runtime.jobs import JobMessage
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

    inspection = _inspect_export_job(
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

    inspection = _inspect_export_job(
        manifest_path,
        job_id="job_1",
        thread_id="thread_1",
    )

    assert inspection.terminal is False
    assert inspection.total_chunks == "?"
    assert isinstance(inspection.progress_error, json.JSONDecodeError)


def test_persist_export_failure_updates_attempt_state(tmp_path: Path) -> None:
    manifest_path, _ = _job_paths(tmp_path)
    write_json_atomic(
        manifest_path,
        _manifest(attempts=4).to_wire(),
    )

    updated = _persist_export_failure(
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
    state._export_queue.put(  # pyright: ignore[reportPrivateUsage]
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
    assert event.metadata == {"job_id": "job_1", "thread_id": "thread_1"}


def test_worker_logs_state_persistence_failure_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, progress_path = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest().to_wire())
    write_json_atomic(
        progress_path,
        ReasonOutputProgress(
            job_id="job_1",
            thread_id="thread_1",
            status="planned",
            completed_chunks=(),
            total_chunks=1,
            pdf_status="pending",
            pdf_path=None,
            updated_at="2026-01-01T00:00:00+00:00",
        ).to_wire(),
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
        "nuself.daemon.server._persist_export_failure",
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
    assert state._export_timers == []  # pyright: ignore[reportPrivateUsage]
