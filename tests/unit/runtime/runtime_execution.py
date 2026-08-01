import threading
from contextvars import ContextVar

import pytest
from pytest import MonkeyPatch

from nuself.runtime.execution import (
    CallOutcome,
    CancellationCleanupError,
    OwnedCall,
    current_cancellation,
)
from nuself.runtime.context import (
    RuntimeContext,
    current_runtime_context,
    runtime_context,
)


def test_owned_call_runs_once_and_returns_value() -> None:
    calls: list[str] = []
    call = OwnedCall(name="test-call", target=lambda: calls.append("run") or 7)

    assert call.start() is True
    assert call.start() is False
    assert call.outcome(timeout=1) == CallOutcome(value=7)
    assert call.alive is False
    assert calls == ["run"]


def test_owned_call_supports_none_as_a_completed_value() -> None:
    call = OwnedCall[None](name="test-call", target=lambda: None)
    call.start()

    assert call.outcome(timeout=1) == CallOutcome(value=None)


def test_owned_call_captures_complete_construction_context() -> None:
    marker = ContextVar("owned_call_test_marker", default="default")
    with runtime_context(request_id="captured", source="client"):
        token = marker.set("captured")
        try:
            call = OwnedCall(
                name="test-call",
                target=lambda: (current_runtime_context(), marker.get()),
            )
        finally:
            marker.reset(token)

    with runtime_context(request_id="invoker", source="test"):
        call.start()
        assert call.outcome(timeout=1) == CallOutcome(
            value=(
                RuntimeContext(request_id="captured", source="client"),
                "captured",
            )
        )
        assert current_runtime_context() == RuntimeContext(
            request_id="invoker",
            source="test",
        )
        assert marker.get() == "default"


def test_owned_call_preserves_control_exception_identity_and_traceback() -> None:
    root = RuntimeError("root")
    control = KeyboardInterrupt("stop")

    def fail() -> int:
        raise control from root

    call = OwnedCall(name="test-call", target=fail)
    call.start()

    outcome = call.outcome(timeout=1)
    error = outcome.error

    assert error is not None
    assert error is control
    assert error.__cause__ is root
    assert error.__traceback__ is not None


def test_owned_call_timeout_does_not_consume_later_outcome() -> None:
    release = threading.Event()

    def wait_for_release() -> str:
        release.wait()
        return "done"

    call = OwnedCall(
        name="test-call",
        target=wait_for_release,
    )
    call.start()

    assert call.wait(timeout=0) is False
    with pytest.raises(TimeoutError, match="still running"):
        call.outcome(timeout=0)

    release.set()
    assert call.outcome(timeout=1) == CallOutcome(value="done")


def test_owned_call_cancel_releases_registered_resource() -> None:
    started = threading.Event()
    released = threading.Event()

    def wait_for_cancellation() -> str:
        cancellation = current_cancellation()
        assert cancellation is not None
        unregister = cancellation.register(released.set)
        started.set()
        try:
            released.wait()
            return "closed"
        finally:
            unregister()

    call = OwnedCall(
        name="test-call",
        target=wait_for_cancellation,
    )
    call.start()
    assert started.wait(timeout=1)

    assert call.cancel() is True
    assert call.cancel() is False
    assert call.outcome(timeout=1) == CallOutcome(value="closed")


def test_owned_call_cancel_attempts_every_registered_closer() -> None:
    ready = threading.Event()
    release = threading.Event()
    calls: list[str] = []

    def wait() -> None:
        cancellation = current_cancellation()
        assert cancellation is not None
        cancellation.register(
            lambda: calls.append("first")
        )

        def fail() -> None:
            calls.append("second")
            raise OSError("close failed")

        def finish() -> None:
            calls.append("third")
            release.set()

        cancellation.register(fail)
        cancellation.register(finish)
        ready.set()
        release.wait()

    call = OwnedCall(name="test-call", target=wait)
    call.start()
    assert ready.wait(timeout=1)

    with pytest.raises(CancellationCleanupError) as captured:
        call.cancel()

    assert calls == ["first", "second", "third"]
    assert len(captured.value.failures) == 1
    assert call.wait(timeout=1)


@pytest.mark.parametrize("timeout", [-1, float("inf"), float("nan"), True])
def test_owned_call_rejects_invalid_timeout(timeout: float) -> None:
    call = OwnedCall(name="test-call", target=lambda: 1)

    with pytest.raises(ValueError, match="finite and non-negative"):
        call.wait(timeout)


def test_owned_call_rolls_back_failed_thread_start(
    monkeypatch: MonkeyPatch,
) -> None:
    original_start = threading.Thread.start
    attempts = 0

    def fail_once(thread: threading.Thread) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("start failed")
        original_start(thread)

    monkeypatch.setattr(threading.Thread, "start", fail_once)
    call = OwnedCall(name="test-call", target=lambda: 1)

    with pytest.raises(RuntimeError, match="start failed"):
        call.start()

    assert call.start() is True
    assert call.outcome(timeout=1) == CallOutcome(value=1)


def test_call_outcome_requires_exactly_one_branch() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        CallOutcome[int]()
    with pytest.raises(ValueError, match="exactly one"):
        CallOutcome(value=1, error=RuntimeError("bad"))
