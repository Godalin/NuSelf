# pyright: reportPrivateUsage=false
from __future__ import annotations

from multiprocessing.context import SpawnContext
from multiprocessing.synchronize import Event
from pathlib import Path
from typing import IO, cast
import multiprocessing

import pytest

from nuself.memory.curator_contract import MemoryAction
from nuself.memory.curator_plan import (
    MemoryCuratorPlan,
    MemoryCuratorPlanLock,
    MemoryCuratorPlanLockCleanupError,
    MemoryCuratorPlanLockContended,
    MemoryCuratorPlanStore,
)


def _plan(thread_id: str = "default") -> MemoryCuratorPlan:
    return MemoryCuratorPlan(
        thread_id=thread_id,
        source_start=0,
        source_end=1,
        observed_at="2026-07-29T00:00:00+00:00",
        actions=(
            MemoryAction(
                action="ignore",
                title="",
                body="",
                reason="cross-process lock test",
            ),
        ),
    )


def _hold_curator_lock(
    project_root: str,
    thread_id: str,
    ready: Event,
    release: Event,
) -> None:
    store = MemoryCuratorPlanStore(Path(project_root))
    with store.exclusive(thread_id):
        ready.set()
        if not release.wait(timeout=10):
            raise RuntimeError("parent did not release curator lock test child")


def test_plan_lock_excludes_other_process_and_retains_plan(
    tmp_path: Path,
) -> None:
    store = MemoryCuratorPlanStore(tmp_path)
    plan = store.save(_plan())
    context: SpawnContext = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_curator_lock,
        args=(str(tmp_path), "default", ready, release),
    )
    process.start()
    try:
        assert ready.wait(timeout=10)
        with pytest.raises(MemoryCuratorPlanLockContended):
            store.discard("default")
        assert store.get("default") == plan
    finally:
        release.set()
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join(timeout=10)

    assert process.exitcode == 0
    store.discard("default")
    assert store.get("default") is None


def test_plan_locks_are_per_thread_and_stable_after_exception(
    tmp_path: Path,
) -> None:
    store = MemoryCuratorPlanStore(tmp_path)
    default_lock = store.exclusive("default")
    other_lock = store.exclusive("other")

    with pytest.raises(RuntimeError, match="operation failed"):
        with default_lock:
            with other_lock:
                raise RuntimeError("operation failed")

    assert default_lock.acquired is False
    assert other_lock.acquired is False
    assert default_lock.path.exists()
    assert other_lock.path.exists()
    with store.exclusive("default"):
        pass


class _FailingCloseHandle:
    def fileno(self) -> int:
        return 42

    def close(self) -> None:
        raise OSError("close failed")


def test_plan_lock_acquire_preserves_contention_and_cleanup_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nuself.memory.curator_plan as plan_module

    handle = _FailingCloseHandle()

    def fake_open(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[str]:
        return cast(IO[str], handle)

    def contend(fd: int, operation: int) -> None:
        raise BlockingIOError("busy")

    monkeypatch.setattr(Path, "open", fake_open)
    monkeypatch.setattr(plan_module, "flock", contend)
    lock = MemoryCuratorPlanLock(tmp_path / "default.lock")

    with pytest.raises(MemoryCuratorPlanLockCleanupError) as captured:
        lock.acquire()

    error = captured.value
    assert error.operation == "acquire"
    assert isinstance(
        error.primary_error,
        MemoryCuratorPlanLockContended,
    )
    assert str(error.cleanup_error) == "close failed"
    assert error.__cause__ is error.primary_error
    assert lock.acquired is False


def test_plan_lock_release_preserves_unlock_and_cleanup_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nuself.memory.curator_plan as plan_module

    handle = _FailingCloseHandle()

    def fail_unlock(fd: int, operation: int) -> None:
        raise OSError("unlock failed")

    monkeypatch.setattr(plan_module, "flock", fail_unlock)
    lock = MemoryCuratorPlanLock(tmp_path / "default.lock")
    lock._handle = cast(IO[str], handle)

    with pytest.raises(MemoryCuratorPlanLockCleanupError) as captured:
        lock.release()

    error = captured.value
    assert error.operation == "release"
    assert str(error.primary_error) == "unlock failed"
    assert str(error.cleanup_error) == "close failed"
    assert error.__cause__ is error.primary_error
    assert lock.acquired is False
