from __future__ import annotations

import threading
import time

import pytest

from nuself.daemon.scheduler import (
    DaemonScheduler,
    DaemonSchedulerCapacityError,
    DaemonSchedulerStoppedError,
    DaemonTask,
)
from nuself.runtime.context import current_runtime_context, runtime_context


def test_scheduler_coalesces_one_stable_identity() -> None:
    release = threading.Event()
    calls: list[str] = []

    def run(task: DaemonTask) -> str:
        calls.append(task.identity)
        release.wait(1)
        return "done"

    scheduler = DaemonScheduler({"test": run})
    scheduler.start()
    first = scheduler.submit(DaemonTask("test", "same", "resource:a"))
    second = scheduler.submit(DaemonTask("test", "same", "resource:a"))

    assert first.admission == "admitted"
    assert second.admission == "coalesced"
    assert second.completion is first.completion
    release.set()
    assert first.completion.result(timeout=1) == "done"
    scheduler.shutdown()
    assert calls == ["same"]


def test_scheduler_serializes_same_resource_but_runs_unrelated_work() -> None:
    first_started = threading.Event()
    unrelated_started = threading.Event()
    release = threading.Event()
    active = 0
    maximum = 0
    lock = threading.Lock()

    def run(task: DaemonTask) -> None:
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        if task.identity == "first":
            first_started.set()
        if task.identity == "unrelated":
            unrelated_started.set()
        release.wait(1)
        with lock:
            active -= 1

    scheduler = DaemonScheduler({"test": run}, max_concurrency=3)
    scheduler.start()
    first = scheduler.submit(DaemonTask("test", "first", "thread:a"))
    second = scheduler.submit(DaemonTask("test", "second", "thread:a"))
    unrelated = scheduler.submit(
        DaemonTask("test", "unrelated", "thread:b")
    )

    assert first_started.wait(1)
    assert unrelated_started.wait(1)
    assert not second.completion.done()
    assert maximum == 2
    release.set()
    first.completion.result(timeout=1)
    second.completion.result(timeout=1)
    unrelated.completion.result(timeout=1)
    scheduler.shutdown()


def test_scheduler_priority_bypasses_a_blocked_resource() -> None:
    started = threading.Event()
    release = threading.Event()
    order: list[str] = []

    def run(task: DaemonTask) -> None:
        order.append(task.identity)
        if task.identity == "running":
            started.set()
            release.wait(1)

    scheduler = DaemonScheduler({"test": run}, max_concurrency=2)
    scheduler.start()
    running = scheduler.submit(
        DaemonTask("test", "running", "resource:a")
    )
    assert started.wait(1)
    blocked = scheduler.submit(
        DaemonTask("test", "blocked", "resource:a", priority=0)
    )
    ready = scheduler.submit(
        DaemonTask("test", "ready", "resource:b", priority=10)
    )
    ready.completion.result(timeout=1)
    assert order == ["running", "ready"]
    release.set()
    running.completion.result(timeout=1)
    blocked.completion.result(timeout=1)
    scheduler.shutdown()


def test_scheduler_repeats_after_completion_without_overlap() -> None:
    called = threading.Event()
    calls = 0

    def run(task: DaemonTask) -> None:
        nonlocal calls
        calls += 1
        if calls >= 2:
            called.set()

    scheduler = DaemonScheduler({"tick": run})
    scheduler.start()
    first = scheduler.submit(
        DaemonTask("tick", "tick", "schedule:tick"),
        interval_seconds=0.01,
    )
    first.completion.result(timeout=1)
    assert called.wait(1)
    scheduler.shutdown()
    assert calls >= 2


def test_scheduler_replaces_task_source_and_preserves_correlation() -> None:
    observed = None

    def run(task: DaemonTask) -> None:
        nonlocal observed
        observed = current_runtime_context()

    scheduler = DaemonScheduler({"chat.turn": run})
    scheduler.start()
    with runtime_context(
        thread_id="thread-1",
        turn_id="turn-1",
        request_id="request-1",
        source="request",
    ):
        submitted = scheduler.submit(
            DaemonTask("chat.turn", "turn-1", "thread:thread-1")
        )
    submitted.completion.result(timeout=1)
    scheduler.shutdown()
    assert observed is not None
    assert observed.thread_id == "thread-1"
    assert observed.turn_id == "turn-1"
    assert observed.request_id == "request-1"
    assert observed.source == "daemon.task.chat.turn"


def test_scheduler_bounds_admission_and_cancels_pending_shutdown() -> None:
    started = threading.Event()
    release = threading.Event()

    def run(task: DaemonTask) -> None:
        started.set()
        release.wait(1)

    scheduler = DaemonScheduler(
        {"test": run}, max_concurrency=1, queue_capacity=2
    )
    scheduler.start()
    running = scheduler.submit(DaemonTask("test", "one", "resource:one"))
    assert started.wait(1)
    pending = scheduler.submit(DaemonTask("test", "two", "resource:two"))
    with pytest.raises(DaemonSchedulerCapacityError):
        scheduler.submit(DaemonTask("test", "three", "resource:three"))

    stopped = threading.Event()

    def stop() -> None:
        scheduler.shutdown()
        stopped.set()

    stopper = threading.Thread(target=stop)
    stopper.start()
    deadline = time.monotonic() + 1
    while not pending.completion.cancelled() and time.monotonic() < deadline:
        time.sleep(0.001)
    assert pending.completion.cancelled()
    release.set()
    running.completion.result(timeout=1)
    stopper.join(1)
    assert stopped.is_set()
    with pytest.raises(DaemonSchedulerStoppedError):
        scheduler.submit(DaemonTask("test", "late", "resource:late"))
