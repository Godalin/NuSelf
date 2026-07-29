from __future__ import annotations

import threading
from pathlib import Path

import pytest

from nuself.daemon.workers import (
    DaemonWorkerReadinessError,
    DaemonWorkerRegistrationError,
    DaemonWorkerSupervisor,
)
from nuself.logs import read_log_events, runtime_event_log_sink
from nuself.runtime import (
    EventPublisher,
    RuntimeContext,
    current_runtime_context,
    runtime_context,
)


def _supervisor(tmp_path: Path) -> DaemonWorkerSupervisor:
    publisher = EventPublisher()
    publisher.attach_projection(runtime_event_log_sink(tmp_path))
    return DaemonWorkerSupervisor(
        tmp_path,
        threading.Event(),
        publisher,
    )


def test_worker_registration_is_unique_and_sealed(
    tmp_path: Path,
) -> None:
    supervisor = _supervisor(tmp_path)
    supervisor.register(
        "worker",
        thread_name="test-worker",
        target=lambda: None,
    )

    with pytest.raises(
        DaemonWorkerRegistrationError,
        match="already registered",
    ):
        supervisor.register(
            "worker",
            thread_name="duplicate-worker",
            target=lambda: None,
        )
    with pytest.raises(
        DaemonWorkerRegistrationError,
        match="not sealed",
    ):
        supervisor.start("worker")

    supervisor.seal()

    with pytest.raises(
        DaemonWorkerRegistrationError,
        match="is sealed",
    ):
        supervisor.register(
            "late",
            thread_name="late-worker",
            target=lambda: None,
        )
    with pytest.raises(
        DaemonWorkerRegistrationError,
        match="unknown daemon worker",
    ):
        supervisor.start("missing")


def test_worker_iteration_replaces_ambient_context_and_updates_health(
    tmp_path: Path,
) -> None:
    supervisor = _supervisor(tmp_path)
    supervisor.register(
        "worker",
        thread_name="test-worker",
        target=lambda: None,
    )
    supervisor.seal()
    observed: list[RuntimeContext] = []

    def operation() -> None:
        observed.append(current_runtime_context())

    with runtime_context(
        request_id="ambient-request",
        thread_id="ambient-thread",
        job_id="ambient-job",
        trace_id="ambient-trace",
        source="test",
    ):
        assert supervisor.run_iteration(
            "worker",
            operation,
            error_event="worker_iteration_failed",
            error_message="worker iteration failed",
        )
        assert current_runtime_context() == RuntimeContext(
            request_id="ambient-request",
            thread_id="ambient-thread",
            job_id="ambient-job",
            trace_id="ambient-trace",
            source="test",
        )

    assert len(observed) == 1
    assert observed[0].source == "daemon.worker.worker"
    assert observed[0].job_id is not None
    assert observed[0].request_id is None
    assert observed[0].thread_id is None
    assert observed[0].trace_id is None
    health = supervisor.health()[0]
    assert health.last_success_at is not None
    assert health.last_error is None
    assert health.consecutive_failures == 0


def test_worker_lifecycle_subscriber_failure_does_not_skip_target_or_stop(
    tmp_path: Path,
) -> None:
    publisher = EventPublisher()
    publisher.attach_projection(runtime_event_log_sink(tmp_path))
    shutdown_requested = threading.Event()

    def fail_subscriber(_event: object) -> None:
        raise RuntimeError("subscriber unavailable")

    publisher.attach_projection(fail_subscriber)
    supervisor = DaemonWorkerSupervisor(
        tmp_path,
        shutdown_requested,
        publisher,
    )
    ran = threading.Event()

    def graceful_target() -> None:
        ran.set()
        shutdown_requested.set()

    supervisor.register(
        "worker",
        thread_name="test-worker-events",
        target=graceful_target,
    )
    supervisor.seal()

    supervisor.start("worker")
    supervisor.join("worker", timeout=1)

    assert ran.is_set()
    lifecycle = [
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="daemon",
        )
        if event.event.startswith("worker.")
    ]
    assert [event.event for event in lifecycle] == [
        "worker.started",
        "worker.stopped",
    ]
    assert all(event.event_id is not None for event in lifecycle)
    assert all(event.source == "daemon.worker.worker" for event in lifecycle)
    health = supervisor.health()[0]
    assert health.last_error is None
    assert health.consecutive_failures == 0


def test_worker_return_before_shutdown_records_unexpected_exit(
    tmp_path: Path,
) -> None:
    supervisor = _supervisor(tmp_path)
    supervisor.register(
        "worker",
        thread_name="test-worker-premature-return",
        target=lambda: None,
    )
    supervisor.seal()

    supervisor.start("worker")
    supervisor.join("worker", timeout=1)

    health = supervisor.health()[0]
    assert health.alive is False
    assert health.last_error == "worker returned before daemon shutdown"
    assert health.consecutive_failures == 1
    lifecycle = [
        event
        for event in read_log_events(
            project_root=tmp_path,
            component="daemon",
        )
        if event.event.startswith("worker.")
    ]
    assert [event.event for event in lifecycle] == [
        "worker.started",
        "worker.failed",
        "worker.stopped",
    ]
    failed = lifecycle[1]
    assert failed.error == "worker returned before daemon shutdown"
    assert failed.metadata == {
        "worker": "worker",
        "operation_event": "worker_exited_unexpectedly",
        "error_type": "DaemonWorkerUnexpectedExitError",
    }
    with pytest.raises(
        DaemonWorkerReadinessError,
        match="worker=stopped",
    ):
        supervisor.require_all_running()


def test_worker_readiness_requires_every_registration_alive(
    tmp_path: Path,
) -> None:
    shutdown_requested = threading.Event()
    supervisor = DaemonWorkerSupervisor(
        tmp_path,
        shutdown_requested,
        EventPublisher(),
    )
    release = threading.Event()

    def wait_for_release() -> None:
        release.wait()

    supervisor.register(
        "first",
        thread_name="test-worker-ready-first",
        target=wait_for_release,
    )
    supervisor.register(
        "second",
        thread_name="test-worker-ready-second",
        target=wait_for_release,
    )
    supervisor.seal()

    supervisor.start("first")
    with pytest.raises(
        DaemonWorkerReadinessError,
        match="second=new",
    ):
        supervisor.require_all_running()

    supervisor.start("second")
    supervisor.require_all_running()

    shutdown_requested.set()
    release.set()
    supervisor.join("first", timeout=1)
    supervisor.join("second", timeout=1)


def test_worker_readiness_rejects_requested_shutdown_while_alive(
    tmp_path: Path,
) -> None:
    shutdown_requested = threading.Event()
    supervisor = DaemonWorkerSupervisor(
        tmp_path,
        shutdown_requested,
        EventPublisher(),
    )
    release = threading.Event()

    def wait_for_release() -> None:
        release.wait()

    supervisor.register(
        "worker",
        thread_name="test-worker-shutdown-race",
        target=wait_for_release,
    )
    supervisor.seal()
    supervisor.start("worker")
    assert supervisor.snapshot("worker").alive is True

    shutdown_requested.set()
    with pytest.raises(
        DaemonWorkerReadinessError,
        match="shutdown was requested before readiness",
    ):
        supervisor.require_all_running()

    release.set()
    supervisor.join("worker", timeout=1)
