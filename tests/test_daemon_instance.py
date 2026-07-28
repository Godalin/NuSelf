# pyright: reportPrivateUsage=false
"""Daemon cross-process instance ownership tests."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import IO, cast

import pytest

from nuself.config import runtime_paths
from nuself.daemon.instance import (
    DaemonInstanceLock,
    DaemonInstanceLockCleanupError,
    DaemonInstanceLockContended,
)
from nuself.logs import read_log_events


def test_instance_lock_contends_then_releases(tmp_path: Path) -> None:
    lock_path = tmp_path / "private" / "runtime" / "nuself.lock"
    owner = DaemonInstanceLock(lock_path)
    contender = DaemonInstanceLock(lock_path)

    owner.acquire()
    assert owner.acquired is True
    with pytest.raises(DaemonInstanceLockContended):
        contender.acquire()

    owner.release()
    assert owner.acquired is False
    contender.acquire()
    assert contender.acquired is True
    contender.release()
    assert lock_path.exists()


class _FakeLockHandle:
    def __init__(self, close_error: BaseException | None = None) -> None:
        self.close_error = close_error
        self.close_calls = 0

    def fileno(self) -> int:
        return 42

    def close(self) -> None:
        self.close_calls += 1
        if self.close_error is not None:
            raise self.close_error


@pytest.mark.parametrize(
    ("flock_error", "primary_type"),
    [
        (BlockingIOError("contended"), DaemonInstanceLockContended),
        (OSError("flock failed"), OSError),
        (KeyboardInterrupt(), KeyboardInterrupt),
    ],
)
def test_instance_lock_acquire_retains_flock_and_close_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    flock_error: BaseException,
    primary_type: type[BaseException],
) -> None:
    import nuself.daemon.instance as instance_module

    handle = _FakeLockHandle(OSError("close failed"))
    lock = DaemonInstanceLock(tmp_path / "runtime" / "nuself.lock")

    def fake_open(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[str]:
        return cast(IO[str], handle)

    monkeypatch.setattr(
        Path,
        "open",
        fake_open,
    )

    def fail_flock(fd: int, operation: int) -> None:
        raise flock_error

    monkeypatch.setattr(instance_module, "flock", fail_flock)

    with pytest.raises(DaemonInstanceLockCleanupError) as captured:
        lock.acquire()

    error = captured.value
    assert error.operation == "acquire"
    assert isinstance(error.primary_error, primary_type)
    assert str(error.cleanup_error) == "close failed"
    assert error.__cause__ is error.primary_error
    assert handle.close_calls == 1
    assert lock.acquired is False


def test_instance_lock_acquire_retains_single_system_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import nuself.daemon.instance as instance_module

    handle = _FakeLockHandle()
    lock = DaemonInstanceLock(tmp_path / "runtime" / "nuself.lock")

    def fake_open(
        path: Path,
        mode: str = "r",
        buffering: int = -1,
        encoding: str | None = None,
        errors: str | None = None,
        newline: str | None = None,
    ) -> IO[str]:
        return cast(IO[str], handle)

    def fail_flock(fd: int, operation: int) -> None:
        raise OSError("flock failed")

    monkeypatch.setattr(Path, "open", fake_open)
    monkeypatch.setattr(instance_module, "flock", fail_flock)

    with pytest.raises(OSError, match="flock failed"):
        lock.acquire()

    assert handle.close_calls == 1
    assert lock.acquired is False


def test_instance_lock_release_retains_unlock_and_close_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import nuself.daemon.instance as instance_module

    handle = _FakeLockHandle(OSError("close failed"))
    lock = DaemonInstanceLock(tmp_path / "runtime" / "nuself.lock")
    lock._handle = cast(IO[str], handle)

    def fail_unlock(fd: int, operation: int) -> None:
        raise OSError("unlock failed")

    monkeypatch.setattr(instance_module, "flock", fail_unlock)

    with pytest.raises(DaemonInstanceLockCleanupError) as captured:
        lock.release()

    error = captured.value
    assert error.operation == "release"
    assert str(error.primary_error) == "unlock failed"
    assert str(error.cleanup_error) == "close failed"
    assert error.__cause__ is error.primary_error
    assert handle.close_calls == 1
    assert lock.acquired is False


def test_instance_lock_release_retains_single_unlock_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import nuself.daemon.instance as instance_module

    handle = _FakeLockHandle()
    lock = DaemonInstanceLock(tmp_path / "runtime" / "nuself.lock")
    lock._handle = cast(IO[str], handle)

    def fail_unlock(fd: int, operation: int) -> None:
        raise OSError("unlock failed")

    monkeypatch.setattr(instance_module, "flock", fail_unlock)

    with pytest.raises(OSError, match="unlock failed"):
        lock.release()

    assert handle.close_calls == 1
    assert lock.acquired is False


def test_instance_lock_release_retains_single_close_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import nuself.daemon.instance as instance_module

    handle = _FakeLockHandle(OSError("close failed"))
    lock = DaemonInstanceLock(tmp_path / "runtime" / "nuself.lock")
    lock._handle = cast(IO[str], handle)

    def unlock(fd: int, operation: int) -> None:
        return None

    monkeypatch.setattr(
        instance_module,
        "flock",
        unlock,
    )

    with pytest.raises(OSError, match="close failed"):
        lock.release()

    assert handle.close_calls == 1
    assert lock.acquired is False


def test_contended_daemon_preserves_owner_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    paths.socket_path.write_text("owner-socket", encoding="utf-8")
    paths.pid_path.write_text("4321\n", encoding="utf-8")
    owner = DaemonInstanceLock(paths.runtime_dir / "nuself.lock")
    owner.acquire()

    def fail_if_constructed(project_root: Path) -> object:
        raise AssertionError(
            f"daemon state must not be constructed for {project_root}"
        )

    monkeypatch.setattr(
        server_module,
        "DaemonState",
        fail_if_constructed,
    )
    try:
        assert server_module.run_daemon(tmp_path) == 1
    finally:
        owner.release()

    assert paths.socket_path.read_text(encoding="utf-8") == "owner-socket"
    assert paths.pid_path.read_text(encoding="utf-8") == "4321\n"
    events = read_log_events(project_root=tmp_path, component="daemon")
    assert events[-1].event == "instance_lock_contended"
    assert events[-1].status == "skipped"


class _UnstartedDaemonState:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.shutdown_requested = threading.Event()
        self.start_calls: list[str] = []
        self.stop_calls: list[str] = []

    def start_background_memory_curator(self) -> None:
        self.start_calls.append("memory")

    def start_background_reflection_scheduler(self) -> None:
        self.start_calls.append("reflection")

    def start_background_reason_scheduler(self) -> None:
        self.start_calls.append("reason")

    def start_background_export_worker(self) -> None:
        self.start_calls.append("export")

    def start_background_notification_delivery(self) -> None:
        self.start_calls.append("notification")

    def stop_background_memory_curator(self) -> None:
        self.stop_calls.append("memory")

    def stop_background_reflection_scheduler(self) -> None:
        self.stop_calls.append("reflection")

    def stop_background_reason_scheduler(self) -> None:
        self.stop_calls.append("reason")

    def stop_background_export_worker(self) -> None:
        self.stop_calls.append("export")

    def stop_background_notification_delivery(self) -> None:
        self.stop_calls.append("notification")


def test_bind_failure_starts_no_workers_and_cleans_owned_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import signal
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    paths.socket_path.write_text("stale", encoding="utf-8")
    states: list[_UnstartedDaemonState] = []

    def make_state(project_root: Path) -> _UnstartedDaemonState:
        state = _UnstartedDaemonState(project_root)
        states.append(state)
        return state

    def fail_bind(
        socket_path: str,
        handler: object,
        state: object,
    ) -> object:
        assert int(paths.pid_path.read_text(encoding="utf-8")) > 0
        assert list(paths.runtime_dir.glob("nuself.pid.*.tmp")) == []
        raise OSError("bind failed")

    def ignore_signal(
        signal_number: int,
        handler: object,
    ) -> object:
        return handler

    monkeypatch.setattr(server_module, "DaemonState", make_state)
    monkeypatch.setattr(server_module, "NuSelfUnixServer", fail_bind)
    monkeypatch.setattr(signal, "signal", ignore_signal)

    with pytest.raises(OSError, match="bind failed"):
        server_module._run_owned_daemon(paths)

    assert len(states) == 1
    assert states[0].start_calls == []
    assert states[0].stop_calls == [
        "memory",
        "reflection",
        "reason",
        "export",
        "notification",
    ]
    assert not paths.socket_path.exists()
    assert not paths.pid_path.exists()


def test_owned_daemon_attempts_all_cleanup_and_preserves_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import signal
    import nuself.daemon.server as server_module
    import nuself.storage as storage_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    states: list[_UnstartedDaemonState] = []
    reset_roots: list[Path | None] = []

    class FailingCleanupState(_UnstartedDaemonState):
        def stop_background_memory_curator(self) -> None:
            super().stop_background_memory_curator()
            raise RuntimeError("memory stop failed")

        def stop_background_reason_scheduler(self) -> None:
            super().stop_background_reason_scheduler()
            raise RuntimeError("reason stop failed")

    def make_state(project_root: Path) -> FailingCleanupState:
        state = FailingCleanupState(project_root)
        states.append(state)
        return state

    def fail_bind(
        socket_path: str,
        handler: object,
        state: object,
    ) -> object:
        raise OSError("bind failed")

    def fail_reset(project_root: Path | None = None) -> None:
        reset_roots.append(project_root)
        raise RuntimeError("storage reset failed")

    def ignore_signal(
        signal_number: int,
        handler: object,
    ) -> object:
        return handler

    monkeypatch.setattr(server_module, "DaemonState", make_state)
    monkeypatch.setattr(server_module, "NuSelfUnixServer", fail_bind)
    monkeypatch.setattr(storage_module, "reset_default_backend", fail_reset)
    monkeypatch.setattr(
        signal,
        "signal",
        ignore_signal,
    )

    with pytest.raises(server_module.DaemonLifecycleError) as captured:
        server_module._run_owned_daemon(paths)

    assert isinstance(captured.value.__cause__, OSError)
    assert str(captured.value.__cause__) == "bind failed"
    assert captured.value.primary_error is captured.value.__cause__
    assert [failure.step for failure in captured.value.failures] == [
        "worker.memory_curator.stop",
        "worker.reason_scheduler.stop",
        "storage.default_backend.reset",
    ]
    assert states[0].stop_calls == [
        "memory",
        "reflection",
        "reason",
        "export",
        "notification",
    ]
    assert reset_roots == [paths.project_root]
    assert not paths.socket_path.exists()
    assert not paths.pid_path.exists()
    event = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )[-1]
    assert event.event == "shutdown_cleanup_failed"
    assert event.metadata == {
        "steps": (
            "worker.memory_curator.stop",
            "worker.reason_scheduler.stop",
            "storage.default_backend.reset",
        ),
        "primary_failed": True,
    }
    assert event.to_record()["metadata"] == {
        "steps": [
            "worker.memory_curator.stop",
            "worker.reason_scheduler.stop",
            "storage.default_backend.reset",
        ],
        "primary_failed": True,
    }


def test_instance_lock_release_failure_retains_owned_daemon_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nuself.daemon.server as server_module

    class FailingReleaseLock:
        def __init__(self, path: Path) -> None:
            self.path = path

        def acquire(self) -> None:
            return None

        def release(self) -> None:
            raise OSError("lock release failed")

    def fail_owned_daemon(paths: object) -> int:
        raise ValueError("serve failed")

    monkeypatch.setattr(
        server_module,
        "DaemonInstanceLock",
        FailingReleaseLock,
    )
    monkeypatch.setattr(
        server_module,
        "_run_owned_daemon",
        fail_owned_daemon,
    )

    with pytest.raises(server_module.DaemonLifecycleError) as captured:
        server_module.run_daemon(tmp_path)

    assert isinstance(captured.value.__cause__, ValueError)
    assert str(captured.value.__cause__) == "serve failed"
    assert [failure.step for failure in captured.value.failures] == [
        "instance_lock.release"
    ]
    assert isinstance(captured.value.failures[0].error, OSError)


def test_stopped_event_is_written_after_owned_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import signal
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    states: list[_UnstartedDaemonState] = []
    stopped_observed = False

    class ExitingState(_UnstartedDaemonState):
        def start_background_notification_delivery(self) -> None:
            super().start_background_notification_delivery()
            self.shutdown_requested.set()

    class ImmediateServer:
        def __init__(
            self,
            socket_path: str,
            handler: object,
            state: object,
        ) -> None:
            self.timeout = 0.0

        def __enter__(self) -> ImmediateServer:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

        def handle_request(self) -> None:
            raise AssertionError("shutdown was already requested")

    def make_state(project_root: Path) -> ExitingState:
        state = ExitingState(project_root)
        states.append(state)
        return state

    def capture_write(
        component: object,
        event: str,
        message: str,
        **kwargs: object,
    ) -> object:
        nonlocal stopped_observed
        if event == "stopped":
            assert states[0].stop_calls == [
                "memory",
                "reflection",
                "reason",
                "export",
                "notification",
            ]
            assert not paths.socket_path.exists()
            assert not paths.pid_path.exists()
            stopped_observed = True
        return object()

    def ignore_signal(
        signal_number: int,
        handler: object,
    ) -> object:
        return handler

    monkeypatch.setattr(server_module, "DaemonState", make_state)
    monkeypatch.setattr(server_module, "NuSelfUnixServer", ImmediateServer)
    monkeypatch.setattr(server_module, "write_log_event", capture_write)
    monkeypatch.setattr(
        signal,
        "signal",
        ignore_signal,
    )

    assert server_module._run_owned_daemon(paths) == 0
    assert stopped_observed is True


def test_signal_restore_failure_joins_daemon_cleanup_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)

    class FailingSignalOwner:
        def __init__(self, shutdown_requested: threading.Event) -> None:
            self.shutdown_requested = shutdown_requested

        def install(self) -> bool:
            return True

        def restore(self) -> bool:
            raise OSError("signal restore failed")

    def make_state(project_root: Path) -> _UnstartedDaemonState:
        return _UnstartedDaemonState(project_root)

    def fail_bind(
        socket_path: str,
        handler: object,
        state: object,
    ) -> object:
        raise OSError("bind failed")

    monkeypatch.setattr(server_module, "DaemonState", make_state)
    monkeypatch.setattr(
        server_module,
        "DaemonSignalOwner",
        FailingSignalOwner,
    )
    monkeypatch.setattr(server_module, "NuSelfUnixServer", fail_bind)

    with pytest.raises(server_module.DaemonLifecycleError) as captured:
        server_module._run_owned_daemon(paths)

    assert isinstance(captured.value.__cause__, OSError)
    assert str(captured.value.__cause__) == "bind failed"
    assert [failure.step for failure in captured.value.failures] == [
        "signal_handlers.restore"
    ]
    assert isinstance(captured.value.failures[0].error, OSError)
    assert not paths.pid_path.exists()
