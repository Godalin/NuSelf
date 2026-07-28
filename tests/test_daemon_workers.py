from __future__ import annotations

import threading
from pathlib import Path

import pytest

from nuself.daemon.workers import (
    DaemonWorkerRegistrationError,
    DaemonWorkerSupervisor,
)
from nuself.runtime import (
    RuntimeContext,
    current_runtime_context,
    runtime_context,
)


def _supervisor(tmp_path: Path) -> DaemonWorkerSupervisor:
    return DaemonWorkerSupervisor(tmp_path, threading.Event())


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
