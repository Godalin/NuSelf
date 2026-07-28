from __future__ import annotations

import threading
from pathlib import Path

import pytest

from nuself.daemon.workers import (
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
    publisher.subscribe(runtime_event_log_sink(tmp_path))
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
    publisher.subscribe(runtime_event_log_sink(tmp_path))

    def fail_subscriber(_event: object) -> None:
        raise RuntimeError("subscriber unavailable")

    publisher.subscribe(fail_subscriber)
    supervisor = DaemonWorkerSupervisor(
        tmp_path,
        threading.Event(),
        publisher,
    )
    ran = threading.Event()
    supervisor.register(
        "worker",
        thread_name="test-worker-events",
        target=ran.set,
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
