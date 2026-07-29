from __future__ import annotations

from collections.abc import Callable

import pytest

from nuself.runtime.scheduling import DelayedTaskScheduler


class _FakeTimer:
    instances: list[_FakeTimer] = []
    fail_start = False

    def __init__(
        self,
        interval: float,
        function: Callable[..., None],
        args: tuple[object, ...],
    ) -> None:
        self.interval = interval
        self.function = function
        self.args = args
        self.daemon = False
        self.cancelled = False
        self.__class__.instances.append(self)

    def start(self) -> None:
        if self.fail_start:
            raise OSError("timer start failed")

    def cancel(self) -> None:
        self.cancelled = True

    def fire(self) -> None:
        self.function(*self.args)


def _reset_fake_timer() -> None:
    _FakeTimer.instances.clear()
    _FakeTimer.fail_start = False


def test_delayed_scheduler_removes_ownership_before_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_timer()
    monkeypatch.setattr(
        "nuself.runtime.scheduling.threading.Timer",
        _FakeTimer,
    )
    scheduler = DelayedTaskScheduler()
    observed_pending: list[int] = []

    assert scheduler.schedule(
        ("thread-1", "job-1"),
        10,
        lambda: observed_pending.append(scheduler.pending_count),
    )
    assert not scheduler.schedule(
        ("thread-1", "job-1"),
        10,
        lambda: None,
    )
    assert scheduler.pending_count == 1
    assert _FakeTimer.instances[0].daemon is True

    _FakeTimer.instances[0].fire()

    assert observed_pending == [0]
    assert scheduler.pending_count == 0


def test_delayed_scheduler_rolls_back_failed_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_timer()
    monkeypatch.setattr(
        "nuself.runtime.scheduling.threading.Timer",
        _FakeTimer,
    )
    _FakeTimer.fail_start = True
    scheduler = DelayedTaskScheduler()

    with pytest.raises(OSError, match="timer start failed"):
        scheduler.schedule("job-1", 1, lambda: None)

    assert scheduler.pending_count == 0
    assert not scheduler.contains("job-1")
    assert _FakeTimer.instances[0].cancelled


def test_delayed_scheduler_close_cancels_and_blocks_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_fake_timer()
    monkeypatch.setattr(
        "nuself.runtime.scheduling.threading.Timer",
        _FakeTimer,
    )
    scheduler = DelayedTaskScheduler()
    calls = 0

    def callback() -> None:
        nonlocal calls
        calls += 1

    assert scheduler.schedule("job-1", 1, callback)
    timer = _FakeTimer.instances[0]

    assert scheduler.close() == 1
    assert scheduler.close() == 0
    assert timer.cancelled
    assert not scheduler.schedule("job-2", 1, callback)

    timer.fire()
    assert calls == 0
