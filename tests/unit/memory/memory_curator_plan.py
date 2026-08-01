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
)
from nuself.storage import auto_backend
from memory_fixtures import memory_curator_plan_store


def _plan(observation_id: str = "obs_default") -> MemoryCuratorPlan:
    return MemoryCuratorPlan(
        observation_id=observation_id,
        source_ref=f"test:{observation_id}",
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
    observation_id: str,
    ready: Event,
    release: Event,
) -> None:
    root = Path(project_root)
    backend = auto_backend(root)
    try:
        store = memory_curator_plan_store(root, backend=backend)
        with store.exclusive(observation_id):
            ready.set()
            if not release.wait(timeout=10):
                raise RuntimeError(
                    "parent did not release curator lock test child"
                )
    finally:
        backend.close()


def test_plan_lock_excludes_other_process_and_retains_plan(
    tmp_path: Path,
) -> None:
    store = memory_curator_plan_store(tmp_path)
    plan = store.save(_plan())
    context: SpawnContext = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_curator_lock,
        args=(str(tmp_path), "obs_default", ready, release),
    )
    process.start()
    try:
        assert ready.wait(timeout=10)
        with pytest.raises(MemoryCuratorPlanLockContended):
            store.discard("obs_default")
        assert store.get("obs_default") == plan
    finally:
        release.set()
        process.join(timeout=10)
        if process.is_alive():
            process.terminate()
            process.join(timeout=10)

    assert process.exitcode == 0
    store.discard("obs_default")
    assert store.get("obs_default") is None


def test_plan_locks_are_per_thread_and_stable_after_exception(
    tmp_path: Path,
) -> None:
    store = memory_curator_plan_store(tmp_path)
    default_lock = store.exclusive("obs_default")
    other_lock = store.exclusive("obs_other")

    with pytest.raises(RuntimeError, match="operation failed"):
        with default_lock:
            with other_lock:
                raise RuntimeError("operation failed")

    assert default_lock.path.exists()
    assert other_lock.path.exists()
    with store.exclusive("obs_default"):
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
