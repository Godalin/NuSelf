# pyright: reportPrivateUsage=false

import json
import threading
from collections.abc import Callable, Sequence
from pathlib import Path
import time

import pytest
from langchain_core.messages import BaseMessage
from pydantic import ValidationError

from nuself.daemon.reason_export import (
    ReasonExportWorker,
    ReasonSectionOutput,
    ReasonSectionPlanOutput,
    build_reason_export_section_planner,
    inspect_export_job,
    persist_export_failure,
)
from nuself.daemon.workers import DaemonWorkerSupervisor
from nuself.daemon.state import DaemonState
from nuself.logs import LogEvent, read_log_events
from nuself.reason.output import (
    ReasonOutputManifest,
    ReasonOutputProgress,
    ReasonOutputSection,
    ReasonOutputService,
)
from nuself.reason.job_contracts import (
    REASON_OUTPUT_JOB_NAME,
    build_reason_job_definition_registry,
)
from nuself.reason.domain import ReasoningStep, ReasoningThread
from nuself.storage import write_json_atomic
from nuself.runtime import RuntimeContext, RuntimeEnvelope
from nuself.runtime.jobs import JobMessage
from nuself.runtime.job_definitions import UnknownJobDefinitionError
from nuself.runtime.context import runtime_context
from nuself.runtime.events import EventPublisher
from nuself.workspace import PrivateWorkspaceStore


def _job_message(
    *,
    name: str = REASON_OUTPUT_JOB_NAME,
    producer: str,
    job_id: str,
    resource_id: str,
    payload: dict[str, object] | None = None,
) -> JobMessage:
    return build_reason_job_definition_registry().create(
        name=name,
        producer=producer,
        job_id=job_id,
        resource_id=resource_id,
        payload=payload,
    )


def _decoded_job_message(
    *,
    name: str,
    producer: str,
    job_id: str,
    resource_id: str,
) -> JobMessage:
    return JobMessage(
        RuntimeEnvelope(
            kind="job",
            name=name,
            producer=producer,
            context=RuntimeContext(job_id=job_id),
            payload={"resource_id": resource_id, "data": {}},
        )
    )


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


class _SectionAgent:
    def __init__(self, output: ReasonSectionPlanOutput) -> None:
        self.output = output
        self.calls: list[Sequence[BaseMessage]] = []

    def invoke(
        self,
        messages: Sequence[BaseMessage],
    ) -> ReasonSectionPlanOutput:
        self.calls.append(messages)
        return self.output


class _TextAgent:
    def __init__(self, result: str = "Composed section body.") -> None:
        self.result = result
        self.calls: list[Sequence[BaseMessage]] = []

    def invoke(self, messages: Sequence[BaseMessage]) -> str:
        self.calls.append(messages)
        return self.result


def _reason_steps() -> tuple[ReasoningStep, ...]:
    return (
        ReasoningStep(
            id="step-0",
            thread_id="thread-1",
            summary="First step",
        ),
        ReasoningStep(
            id="step-1",
            thread_id="thread-1",
            summary="Second step",
        ),
        ReasoningStep(
            id="step-2",
            thread_id="thread-1",
            summary="Third step",
        ),
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"sections": []},
        {
            "sections": [
                {
                    "title": " ",
                    "focus": "valid",
                    "step_start": 0,
                    "step_end": 0,
                }
            ]
        },
        {
            "sections": [
                {
                    "title": "valid",
                    "focus": "valid",
                    "step_start": "0",
                    "step_end": 0,
                }
            ]
        },
        {
            "sections": [
                {
                    "title": "valid",
                    "focus": "valid",
                    "step_start": 1,
                    "step_end": 0,
                }
            ]
        },
    ],
)
def test_reason_section_plan_output_is_exact(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ReasonSectionPlanOutput.model_validate(payload)


def test_reason_export_section_planner_uses_complete_typed_plan(
    tmp_path: Path,
) -> None:
    agent = _SectionAgent(
        ReasonSectionPlanOutput(
            sections=[
                ReasonSectionOutput(
                    title="Opening",
                    focus="Establish the problem",
                    step_start=0,
                    step_end=1,
                ),
                ReasonSectionOutput(
                    title="Resolution",
                    focus="Conclude the work",
                    step_start=2,
                    step_end=2,
                ),
            ]
        )
    )
    planner = build_reason_export_section_planner(
        tmp_path,
        agent=agent,
    )

    sections = planner(
        ReasoningThread(id="thread-1", topic="Typed export"),
        _reason_steps(),
        "report",
    )

    assert [section.title for section in sections] == [
        "Opening",
        "Resolution",
    ]
    assert sections[0].step_ids == ("step-0", "step-1")
    assert sections[1].step_ids == ("step-2",)
    assert len(agent.calls) == 1
    assert "Return ONLY" not in agent.calls[0][1].text


def test_reason_export_section_planner_rejects_partial_range_plan(
    tmp_path: Path,
) -> None:
    agent = _SectionAgent(
        ReasonSectionPlanOutput(
            sections=[
                ReasonSectionOutput(
                    title="Partial",
                    focus="Skips the final step",
                    step_start=0,
                    step_end=1,
                )
            ]
        )
    )
    planner = build_reason_export_section_planner(
        tmp_path,
        agent=agent,
    )

    sections = planner(
        ReasoningThread(id="thread-1", topic="Fallback export"),
        _reason_steps(),
        "report",
    )

    assert sections
    assert sections[0].title != "Partial"
    assert tuple(
        step_id
        for section in sections
        for step_id in section.step_ids
    ) == ("step-0", "step-1", "step-2")


def test_reason_export_worker_composes_with_injected_text_agent(
    tmp_path: Path,
) -> None:
    shutdown = threading.Event()
    agent = _TextAgent()
    worker = ReasonExportWorker(
        tmp_path,
        shutdown,
        DaemonWorkerSupervisor(
            tmp_path,
            shutdown,
            EventPublisher(),
        ),
        text_agent=agent,
    )
    steps = _reason_steps()
    section = ReasonOutputSection(
        index=0,
        title="Complete section",
        focus="Cover all steps",
        step_ids=tuple(step.id for step in steps),
        source_start_index=0,
        source_end_index=2,
        summary="Complete section",
    )

    result = worker._llm_runner(
        ReasoningThread(id="thread-1", topic="Text export"),
        _manifest(thread_id="thread-1"),
        steps,
        section=section,
        section_plan=(section,),
        index=0,
        total=1,
    )

    assert result == "Composed section body."
    assert len(agent.calls) == 1
    assert "writing assistant" in agent.calls[0][0].text
    assert "Current section: Complete section" in agent.calls[0][1].text
    assert "First step" in agent.calls[0][1].text


def test_reason_export_worker_propagates_text_agent_failure(
    tmp_path: Path,
) -> None:
    class _FailingTextAgent:
        def invoke(self, messages: Sequence[BaseMessage]) -> str:
            del messages
            raise RuntimeError("all configured LLM endpoints failed")

    shutdown = threading.Event()
    worker = ReasonExportWorker(
        tmp_path,
        shutdown,
        DaemonWorkerSupervisor(
            tmp_path,
            shutdown,
            EventPublisher(),
        ),
        text_agent=_FailingTextAgent(),
    )
    steps = _reason_steps()
    section = ReasonOutputSection(
        index=0,
        title="Failure section",
        focus="Must retry",
        step_ids=tuple(step.id for step in steps),
        source_start_index=0,
        source_end_index=2,
        summary="Failure section",
    )

    with pytest.raises(
        RuntimeError,
        match="all configured LLM endpoints failed",
    ):
        worker._llm_runner(
            ReasoningThread(id="thread-1", topic="Failing export"),
            _manifest(thread_id="thread-1"),
            steps,
            section=section,
            section_plan=(section,),
            index=0,
            total=1,
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
            _job_message(
                name="reason.output.export",
                producer="reasoning",
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
    assert event.metadata == {}


def test_worker_rejects_unknown_job_before_queue_mutation(
    tmp_path: Path,
) -> None:
    worker = DaemonState(tmp_path).reason_export_worker
    message = _decoded_job_message(
        name="unknown.job",
        producer="reasoning",
        job_id="job_1",
        resource_id="thread_1",
    )

    with pytest.raises(UnknownJobDefinitionError):
        worker.enqueue(message)

    assert worker._queue.empty()


def test_full_export_admission_recovers_from_durable_manifests_online(
    tmp_path: Path,
) -> None:
    first_manifest, _ = _job_paths(
        tmp_path,
        job_id="a_first",
        thread_id="thread_1",
    )
    second_manifest, _ = _job_paths(
        tmp_path,
        job_id="b_second",
        thread_id="thread_1",
    )
    write_json_atomic(
        first_manifest,
        _manifest(job_id="a_first").to_wire(),
    )
    write_json_atomic(
        second_manifest,
        _manifest(job_id="b_second").to_wire(),
    )
    shutdown = threading.Event()
    worker = ReasonExportWorker(
        tmp_path,
        shutdown,
        DaemonWorkerSupervisor(
            tmp_path,
            shutdown,
            EventPublisher(),
        ),
        text_agent=_TextAgent(),
        queue_capacity=1,
    )
    worker.prepare()
    worker.enqueue(
        _job_message(
            name="reason.output.export",
            producer="reasoning",
            job_id="a_first",
            resource_id="thread_1",
        )
    )
    worker.enqueue(
        _job_message(
            name="reason.output.export",
            producer="reasoning",
            job_id="b_second",
            resource_id="thread_1",
        )
    )
    first = worker._queue.get_nowait()
    assert first.job_id == "a_first"

    write_json_atomic(
        first_manifest,
        _manifest(job_id="a_first", status="complete").to_wire(),
    )
    worker._queue.complete(first)
    store = PrivateWorkspaceStore(tmp_path, scope="reason")
    worker._run_requested_reconciliation(store)

    recovered = worker._queue.get_nowait()
    assert recovered.job_id == "b_second"
    worker._queue.complete(recovered)


def test_reconciliation_does_not_bypass_live_retry_timer(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest(attempts=1).to_wire())
    shutdown = threading.Event()
    worker = ReasonExportWorker(
        tmp_path,
        shutdown,
        DaemonWorkerSupervisor(
            tmp_path,
            shutdown,
            EventPublisher(),
        ),
        text_agent=_TextAgent(),
    )
    worker.prepare()
    assert worker._retry_scheduler.schedule(
        ("thread_1", "job_1"),
        60,
        lambda: None,
    )

    worker._reconcile(PrivateWorkspaceStore(tmp_path, scope="reason"))

    assert worker._queue.empty()
    worker.stop()


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
        _job_message(
            name="reason.output.export",
            producer="reasoning",
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
    assert event.metadata == {}
    assert "secret progress" not in str(event.to_record())


def test_worker_audit_failure_cannot_suppress_durable_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, progress_path = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest().to_wire())
    write_json_atomic(progress_path, _progress().to_wire())
    scheduled: list[
        tuple[Callable[..., None], tuple[object, ...]]
    ] = []

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
            function: Callable[..., None],
            args: tuple[object, ...],
        ) -> None:
            del interval
            scheduled.append((function, args))
            self.daemon = False

        def start(self) -> None:
            return None

        def cancel(self) -> None:
            return None

        def is_alive(self) -> bool:
            return False

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        ReasonOutputService,
        "compose_with_runner",
        compose,
    )
    monkeypatch.setattr(
        "nuself.runtime.scheduling.threading.Timer",
        FakeTimer,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    state = DaemonState(tmp_path)
    worker = state.reason_export_worker
    worker.prepare()
    message = _job_message(
        name="reason.output.export",
        producer="reasoning",
        job_id="job_1",
        resource_id="thread_1",
    )

    with pytest.warns(RuntimeWarning) as captured:
        worker._process(message)

    assert len(scheduled) == 1
    function, args = scheduled[0]
    function(*args)
    retry = worker._queue.get_nowait()
    assert retry.job_id == "job_1"
    worker._queue.complete(retry)
    persisted = ReasonOutputManifest.from_wire(
        json.loads(manifest_path.read_text(encoding="utf-8"))
    )
    assert persisted.attempts == 1
    assert any(
        "runtime/observability_sink_failed" in str(warning.message)
        for warning in captured
    )
    worker.stop()


def test_retry_timer_start_failure_rolls_back_and_requests_reconciliation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, progress_path = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest().to_wire())
    write_json_atomic(progress_path, _progress().to_wire())

    def compose(
        self: ReasonOutputService,
        thread_id: str,
        job_id: str,
        runner: object,
    ) -> ReasonOutputManifest:
        del self, thread_id, job_id, runner
        raise RuntimeError("compose failed")

    class FailingTimer:
        daemon = False

        def __init__(
            self,
            interval: float,
            function: object,
            args: tuple[object, ...],
        ) -> None:
            del interval, function, args
            self.cancelled = False

        def start(self) -> None:
            raise OSError("timer start unavailable")

        def cancel(self) -> None:
            self.cancelled = True

    monkeypatch.setattr(ReasonOutputService, "compose_with_runner", compose)
    monkeypatch.setattr(
        "nuself.runtime.scheduling.threading.Timer",
        FailingTimer,
    )
    state = DaemonState(tmp_path)
    worker = state.reason_export_worker
    worker.prepare()
    worker._process(
        _job_message(
            name="reason.output.export",
            producer="reasoning",
            job_id="job_1",
            resource_id="thread_1",
        )
    )

    assert worker.pending_retry_count == 0
    assert worker._reconciliation_requested.is_set()
    event = [
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="daemon",
        )
        if event.event == "export_retry_schedule_failed"
    ][-1]
    assert event.status == "degraded"
    assert event.metadata == {"attempts": 1, "next_backoff": 10}
    assert "timer start unavailable" in (event.error or "")


def test_progress_diagnostic_failure_cannot_block_composition(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, progress_path = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest().to_wire())
    progress_path.write_text("{", encoding="utf-8")
    composed: list[str] = []

    def compose(
        self: ReasonOutputService,
        thread_id: str,
        job_id: str,
        runner: object,
    ) -> ReasonOutputManifest:
        composed.append(job_id)
        return _manifest(job_id=job_id, thread_id=thread_id)

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        ReasonOutputService,
        "compose_with_runner",
        compose,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    state = DaemonState(tmp_path)
    worker = state.reason_export_worker
    worker.prepare()
    message = _job_message(
        name="reason.output.export",
        producer="reasoning",
        job_id="job_1",
        resource_id="thread_1",
    )

    with pytest.warns(RuntimeWarning) as captured:
        worker._process(message)

    assert composed == ["job_1"]
    assert any(
        (
            "component=daemon event=export_job_progress_invalid "
            "observed_error=Expecting property name enclosed in double quotes"
        )
        in str(warning.message)
        for warning in captured
    )


def test_reconciliation_diagnostic_failure_does_not_truncate_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad_manifest, _ = _job_paths(
        tmp_path,
        job_id="a_bad",
        thread_id="thread_1",
    )
    bad_manifest.write_text("{", encoding="utf-8")
    good_manifest, _ = _job_paths(
        tmp_path,
        job_id="b_good",
        thread_id="thread_1",
    )
    write_json_atomic(
        good_manifest,
        _manifest(job_id="b_good").to_wire(),
    )

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    state = DaemonState(tmp_path)
    worker = state.reason_export_worker
    worker.prepare()
    store = PrivateWorkspaceStore(tmp_path, scope="reason")

    with pytest.warns(RuntimeWarning) as captured:
        worker._reconcile(store)

    queued = worker._queue.get_nowait()
    assert queued.job_id == "b_good"
    assert queued.resource_id == "thread_1"
    assert any(
        "component=daemon event=export_reconciliation_skip"
        in str(warning.message)
        for warning in captured
    )


def test_shutdown_audit_failure_cannot_undo_queue_drain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    state = DaemonState(tmp_path)
    worker = state.reason_export_worker
    worker.enqueue(
        _job_message(
            name="reason.output.export",
            producer="reasoning",
            job_id="job_1",
            resource_id="thread_1",
        )
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        worker.stop()

    assert worker._stopping.is_set()
    assert worker._queue.empty()
    worker.enqueue(
        _job_message(
            name="reason.output.export",
            producer="reasoning",
            job_id="job_2",
            resource_id="thread_1",
        )
    )
    assert worker._queue.empty()


def test_worker_retry_message_inherits_job_correlation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_path, progress_path = _job_paths(tmp_path)
    write_json_atomic(manifest_path, _manifest().to_wire())
    write_json_atomic(progress_path, _progress().to_wire())
    scheduled: list[
        tuple[Callable[..., None], tuple[object, ...]]
    ] = []

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
            function: Callable[..., None],
            args: tuple[object, ...],
        ) -> None:
            del interval
            scheduled.append((function, args))
            self.daemon = False

        def start(self) -> None:
            return None

        def cancel(self) -> None:
            return None

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(ReasonOutputService, "compose_with_runner", compose)
    monkeypatch.setattr(
        "nuself.runtime.scheduling.threading.Timer",
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
    captured: list[JobMessage] = []
    with runtime_context(
        request_id="request-retry",
        turn_id="turn-retry",
        trace_id="trace-retry",
        source="daemon",
    ):
        state.reason_export_worker.enqueue(
            _job_message(
                name="reason.output.export",
                producer="reasoning",
                job_id="job_1",
                resource_id="thread_1",
            )
        )
    def capture_retry(message: JobMessage) -> None:
        captured.append(message)

    monkeypatch.setattr(
        state.reason_export_worker,
        "enqueue",
        capture_retry,
    )

    state.start_background_export_worker()
    event = _wait_for_event(tmp_path, "export_job_retry")
    assert len(scheduled) == 1
    function, args = scheduled[0]
    function(*args)
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
    scheduled: list[object] = []

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
            args: tuple[object, ...],
        ) -> None:
            del interval, function
            scheduled.extend(args)
            self.daemon = False

        def start(self) -> None:
            return None

        def cancel(self) -> None:
            return None

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(ReasonOutputService, "compose_with_runner", compose)
    monkeypatch.setattr(
        "nuself.runtime.scheduling.threading.Timer",
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
    assert event.metadata == {}
    assert state.reason_export_worker.pending_retry_count == 0
