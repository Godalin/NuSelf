from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path

import pytest

from nuself.daemon.state import DaemonState as _DaemonState
from daemon_fixtures import DaemonStateOwner
from nuself.reason.job_contracts import (
    REASON_OUTPUT_JOB_NAME,
    build_reason_job_definition_registry,
)
from nuself.reason.output_contracts import ReasonOutputManifest
from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
    runtime_context,
)
from nuself.runtime.job_definitions import UnknownJobDefinitionError
from nuself.runtime.jobs import JobMessage
from nuself.storage import write_json_atomic

_STATE_OWNER = DaemonStateOwner()


def DaemonState(project_root: Path) -> _DaemonState:
    return _STATE_OWNER.create(project_root)


@pytest.fixture(autouse=True)
def _close_states():  # pyright: ignore[reportUnusedFunction]
    yield
    _STATE_OWNER.close()


def _message(
    *,
    job_id: str = "job-1",
    thread_id: str = "thread-1",
    producer: str = "reasoning",
) -> JobMessage:
    return build_reason_job_definition_registry().create(
        name=REASON_OUTPUT_JOB_NAME,
        producer=producer,
        job_id=job_id,
        resource_id=thread_id,
    )


def _manifest(
    *,
    job_id: str = "job-1",
    thread_id: str = "thread-1",
) -> ReasonOutputManifest:
    return ReasonOutputManifest(
        job_id=job_id,
        thread_id=thread_id,
        mode="report",
        output_format="markdown",
        source_start_index=0,
        source_end_index=None,
        source_step_ids=(),
        segment_size=20,
    )


def _manifest_path(
    state: _DaemonState,
    *,
    job_id: str = "job-1",
    thread_id: str = "thread-1",
) -> Path:
    return (
        state.application.paths.exports_dir
        / "reason"
        / thread_id
        / "jobs"
        / job_id
        / "manifest.json"
    )


def test_export_wakeups_share_the_unified_scheduler_identity(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    message = _message()

    state.reason_export_service.enqueue(message)
    state.reason_export_service.enqueue(message)

    snapshot = state.scheduler.snapshot()
    assert snapshot.pending == 1
    assert snapshot.in_flight == 0
    state.stop_background_tasks()


def test_export_task_uses_reason_resource_and_job_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = DaemonState(tmp_path)
    observed: list[RuntimeContext] = []

    def process(message: JobMessage) -> None:
        assert message.job_id == "job-1"
        observed.append(current_runtime_context())

    monkeypatch.setattr(state.reason_export_service, "process", process)
    with runtime_context(
        request_id="request-1",
        turn_id="turn-1",
        trace_id="trace-1",
    ):
        state.reason_export_service.enqueue(_message())
    state.scheduler.start()
    deadline = time.monotonic() + 1
    while not observed and time.monotonic() < deadline:
        time.sleep(0.001)
    state.stop_background_tasks()

    assert len(observed) == 1
    assert observed[0] == RuntimeContext(
        reason_id="thread-1",
        request_id="request-1",
        turn_id="turn-1",
        job_id="job-1",
        trace_id="trace-1",
        source="daemon.task.reason.export",
    )


def test_export_recovery_admits_incomplete_manifest_once(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    path = _manifest_path(state)
    write_json_atomic(path, _manifest().to_wire())
    state.reason_export_service.recover()
    state.reason_export_service.recover()

    assert state.scheduler.snapshot().pending == 1
    state.stop_background_tasks()


def test_export_recovery_ignores_terminal_manifest(
    tmp_path: Path,
) -> None:
    state = DaemonState(tmp_path)
    path = _manifest_path(state)
    write_json_atomic(
        path,
        replace(_manifest(), status="complete").to_wire(),
    )
    state.reason_export_service.recover()

    assert state.scheduler.snapshot().pending == 0
    state.stop_background_tasks()


def test_export_rejects_unknown_job_before_scheduler_admission(
    tmp_path: Path,
) -> None:
    from nuself.runtime.messages import RuntimeEnvelope

    state = DaemonState(tmp_path)
    unknown = JobMessage(
        RuntimeEnvelope(
            kind="job",
            name="unknown.job",
            producer="reasoning",
            context=RuntimeContext(job_id="job-1"),
            payload={"resource_id": "thread-1", "data": {}},
        )
    )

    with pytest.raises(UnknownJobDefinitionError):
        state.reason_export_service.enqueue(unknown)
    assert state.scheduler.snapshot().pending == 0
    state.stop_background_tasks()
