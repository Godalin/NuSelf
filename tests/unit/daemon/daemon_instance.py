# pyright: reportPrivateUsage=false
"""Daemon cross-process instance ownership tests."""

from __future__ import annotations

from pathlib import Path
import threading
from typing import IO, cast

import pytest

from nuself.config.settings import runtime_paths
from nuself.daemon.instance import (
    DaemonInstanceLock,
    DaemonInstanceLockCleanupError,
    DaemonInstanceLockContended,
)
from nuself.log.reader import read_log_events
from nuself.config.scope import NuSelfScope


def test_daemon_entrypoint_reconstructs_workspace_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nuself.daemon.server as server_module

    user_root = tmp_path / "user"
    workspace_root = tmp_path / "workspace"
    captured: NuSelfScope | None = None

    def run(scope: NuSelfScope) -> int:
        nonlocal captured
        captured = scope
        return 7

    monkeypatch.setattr(server_module, "run_daemon", run)

    assert server_module.main(
        [
            "--user-root",
            str(user_root),
            "--workspace-root",
            str(workspace_root),
        ]
    ) == 7
    assert captured is not None
    assert captured.kind == "workspace"
    assert captured.user_root == user_root.resolve()
    assert captured.workspace_root == workspace_root.resolve()
    assert captured.root == (workspace_root / ".nuself").resolve()


def test_instance_lock_contends_then_releases(tmp_path: Path) -> None:
    lock_path = tmp_path / "private" / "runtime" / "nuself.lock"
    owner = DaemonInstanceLock(lock_path)
    contender = DaemonInstanceLock(lock_path)

    owner.acquire()
    with pytest.raises(DaemonInstanceLockContended):
        contender.acquire()

    owner.release()
    contender.acquire()
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

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )
    try:
        with pytest.warns(
            RuntimeWarning,
            match="runtime/observability_sink_failed",
        ):
            assert server_module.run_daemon(tmp_path) == 1
    finally:
        owner.release()

    assert paths.socket_path.read_text(encoding="utf-8") == "owner-socket"
    assert paths.pid_path.read_text(encoding="utf-8") == "4321\n"
    assert read_log_events(
        project_root=tmp_path,
        component="daemon",
    ) == []


def test_owned_recovery_removes_stale_socket_and_pid_and_audits(
    tmp_path: Path,
) -> None:
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    paths.socket_path.write_text("crashed socket", encoding="utf-8")
    paths.pid_path.write_text("4321\n", encoding="utf-8")

    server_module._reconcile_stale_runtime_metadata(paths)

    assert not paths.socket_path.exists()
    assert not paths.pid_path.exists()
    event = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )[-1]
    assert event.event == "runtime_metadata_recovered"
    assert event.status == "recovered"
    assert event.metadata == {
        "socket": True,
        "pid": True,
    }
    assert "crashed socket" not in event.message
    assert "4321" not in event.message


def test_owned_recovery_attempts_both_resources_and_retains_failures(
    tmp_path: Path,
) -> None:
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.socket_path.mkdir(parents=True)
    paths.pid_path.parent.mkdir(parents=True)
    paths.pid_path.mkdir()

    with pytest.raises(
        server_module.DaemonRuntimeRecoveryError
    ) as captured:
        server_module._reconcile_stale_runtime_metadata(paths)

    error = captured.value
    assert [failure.step for failure in error.failures] == [
        "stale_socket.unlink",
        "stale_pid.unlink",
    ]
    assert all(
        isinstance(failure.error, OSError)
        for failure in error.failures
    )
    assert error.__cause__ is error.failures[0].error
    assert paths.socket_path.is_dir()
    assert paths.pid_path.is_dir()


def test_recovery_failure_still_runs_owned_metadata_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.socket_path.mkdir(parents=True)
    paths.pid_path.parent.mkdir(parents=True)
    paths.pid_path.mkdir()

    def fail_if_constructed(project_root: Path) -> object:
        raise AssertionError(
            f"daemon state must not be constructed for {project_root}"
        )

    monkeypatch.setattr(
        server_module,
        "DaemonState",
        fail_if_constructed,
    )

    with pytest.raises(server_module.DaemonLifecycleError) as captured:
        server_module._run_owned_daemon(paths)

    error = captured.value
    assert isinstance(
        error.primary_error,
        server_module.DaemonRuntimeRecoveryError,
    )
    assert error.__cause__ is error.primary_error
    assert [
        failure.step for failure in error.primary_error.failures
    ] == [
        "stale_socket.unlink",
        "stale_pid.unlink",
    ]
    assert [failure.step for failure in error.failures] == [
        "socket.unlink",
        "pid.unlink",
    ]


def test_recovery_audit_failure_cannot_restore_stale_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    paths.socket_path.write_text("crashed socket", encoding="utf-8")
    paths.pid_path.write_text("4321\n", encoding="utf-8")

    def fail_log(*args: object, **kwargs: object) -> None:
        raise OSError("audit store unavailable")

    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_log,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        fail_log,
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        server_module._reconcile_stale_runtime_metadata(paths)

    assert not paths.socket_path.exists()
    assert not paths.pid_path.exists()


class _SchedulerSnapshot:
    def __init__(self, running: bool) -> None:
        self.running = running


class _TestScheduler:
    def __init__(self, state: _UnstartedDaemonState) -> None:
        self._state = state
        self.error: RuntimeError | None = None
        self.stop_error: RuntimeError | None = None

    def snapshot(self) -> _SchedulerSnapshot:
        self._state.readiness_checks += 1
        if self.error is not None:
            raise self.error
        return _SchedulerSnapshot(
            running=not self._state.shutdown_requested.is_set()
        )

    def shutdown(self) -> None:
        self._state.stop_calls.append("scheduler")
        if self.stop_error is not None:
            raise self.stop_error


class _UnstartedDaemonState:
    def __init__(self, project_root: Path) -> None:
        self.authority_root = project_root
        self.shutdown_requested = threading.Event()
        self.start_calls: list[str] = []
        self.stop_calls: list[str] = []
        self.readiness_checks = 0
        self.scheduler = _TestScheduler(self)

    def start_background_tasks(self) -> None:
        self.start_calls.append("scheduler")

def test_pid_is_published_only_after_successful_bind(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import signal
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    pid_observed_after_bind = False

    class ExitingState(_UnstartedDaemonState):
        def start_background_tasks(self) -> None:
            nonlocal pid_observed_after_bind
            pid_observed_after_bind = (
                int(paths.pid_path.read_text(encoding="utf-8")) > 0
            )
            super().start_background_tasks()

    class BoundServer:
        def __init__(
            self,
            socket_path: str,
            handler: object,
            state: object,
        ) -> None:
            assert not paths.pid_path.exists()
            assert isinstance(state, ExitingState)
            self.state = state
            self.timeout = 0.0

        def __enter__(self) -> BoundServer:
            assert not paths.pid_path.exists()
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

        def handle_request(self) -> None:
            self.state.shutdown_requested.set()

    def make_state(application: object) -> ExitingState:
        return ExitingState(paths.authority_root)

    def ignore_signal(
        signal_number: int,
        handler: object,
    ) -> object:
        return handler

    monkeypatch.setattr(server_module, "DaemonState", make_state)
    monkeypatch.setattr(server_module, "NuSelfUnixServer", BoundServer)
    monkeypatch.setattr(signal, "signal", ignore_signal)

    server_module._run_owned_daemon(paths)
    assert pid_observed_after_bind is True
    assert not paths.pid_path.exists()


def test_readiness_is_published_after_all_workers_and_before_requests(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import signal
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    states: list[_UnstartedDaemonState] = []
    transitions: list[str] = []

    class OrderedState(_UnstartedDaemonState):
        def start_background_tasks(self) -> None:
            assert int(paths.pid_path.read_text(encoding="utf-8")) > 0
            super().start_background_tasks()

    class OneRequestServer:
        def __init__(
            self,
            socket_path: str,
            handler: object,
            state: object,
        ) -> None:
            assert isinstance(state, OrderedState)
            self.state = state
            self.timeout = 0.0

        def __enter__(self) -> OneRequestServer:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

        def handle_request(self) -> None:
            assert transitions == ["started"]
            transitions.append("request")
            self.state.shutdown_requested.set()

    def make_state(application: object) -> OrderedState:
        state = OrderedState(paths.authority_root)
        states.append(state)
        return state

    def capture_write(envelope: object, **_kwargs: object) -> object:
        event = envelope.name  # type: ignore[union-attr]
        if event == "started":
            assert states[0].start_calls == ["scheduler"]
            assert states[0].readiness_checks == 1
            transitions.append("started")
        elif event == "stopped":
            assert transitions == ["started", "request"]
            transitions.append("stopped")
        return object()

    def ignore_signal(
        signal_number: int,
        handler: object,
    ) -> object:
        return handler

    monkeypatch.setattr(server_module, "DaemonState", make_state)
    monkeypatch.setattr(server_module, "NuSelfUnixServer", OneRequestServer)
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        capture_write,
    )
    monkeypatch.setattr(signal, "signal", ignore_signal)

    server_module._run_owned_daemon(paths)
    assert transitions == ["started", "request", "stopped"]


def test_partial_worker_start_failure_never_publishes_ready_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import signal
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    states: list[_UnstartedDaemonState] = []
    lifecycle_events: list[str] = []
    start_error = RuntimeError("reason worker start failed")

    class FailingState(_UnstartedDaemonState):
        def start_background_tasks(self) -> None:
            super().start_background_tasks()
            raise start_error

    class BoundServer:
        def __init__(
            self,
            socket_path: str,
            handler: object,
            state: object,
        ) -> None:
            paths.socket_path.write_text("bound", encoding="utf-8")

        def __enter__(self) -> BoundServer:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

    def make_state(application: object) -> FailingState:
        state = FailingState(paths.authority_root)
        states.append(state)
        return state

    def capture_write(
        component: object,
        event: str,
        message: str,
        **kwargs: object,
    ) -> object:
        lifecycle_events.append(event)
        return object()

    def ignore_signal(
        signal_number: int,
        handler: object,
    ) -> object:
        return handler

    monkeypatch.setattr(server_module, "DaemonState", make_state)
    monkeypatch.setattr(server_module, "NuSelfUnixServer", BoundServer)
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        capture_write,
    )
    monkeypatch.setattr(signal, "signal", ignore_signal)

    with pytest.raises(RuntimeError) as captured:
        server_module._run_owned_daemon(paths)

    assert captured.value is start_error
    assert lifecycle_events == []
    assert states[0].start_calls == ["scheduler"]
    assert states[0].stop_calls == ["scheduler"]
    assert not paths.socket_path.exists()
    assert not paths.pid_path.exists()


def test_worker_readiness_failure_never_publishes_ready_lifecycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import signal
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    states: list[_UnstartedDaemonState] = []
    lifecycle_events: list[str] = []
    readiness_error = RuntimeError("export worker already stopped")

    class UnreadyState(_UnstartedDaemonState):
        def __init__(self, project_root: Path) -> None:
            super().__init__(project_root)
            self.scheduler.error = readiness_error

    class BoundServer:
        timeout = 0.0

        def __init__(
            self,
            socket_path: str,
            handler: object,
            state: object,
        ) -> None:
            paths.socket_path.write_text("bound", encoding="utf-8")

        def __enter__(self) -> BoundServer:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

    def make_state(application: object) -> UnreadyState:
        state = UnreadyState(paths.authority_root)
        states.append(state)
        return state

    def capture_lifecycle(event: str, **_kwargs: object) -> None:
        lifecycle_events.append(event)

    def ignore_signal(
        signal_number: int,
        handler: object,
    ) -> object:
        return handler

    monkeypatch.setattr(server_module, "DaemonState", make_state)
    monkeypatch.setattr(server_module, "NuSelfUnixServer", BoundServer)
    monkeypatch.setattr(
        server_module,
        "write_lifecycle_audit",
        capture_lifecycle,
    )
    monkeypatch.setattr(
        signal,
        "signal",
        ignore_signal,
    )

    with pytest.raises(RuntimeError) as captured:
        server_module._run_owned_daemon(paths)

    assert captured.value is readiness_error
    assert states[0].readiness_checks == 1
    assert states[0].start_calls == ["scheduler"]
    assert states[0].stop_calls == ["scheduler"]
    assert lifecycle_events == []
    assert not paths.socket_path.exists()
    assert not paths.pid_path.exists()


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

    def make_state(application: object) -> _UnstartedDaemonState:
        state = _UnstartedDaemonState(paths.authority_root)
        states.append(state)
        return state

    def fail_bind(
        socket_path: str,
        handler: object,
        state: object,
    ) -> object:
        assert not paths.pid_path.exists()
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
    assert states[0].stop_calls == ["scheduler"]
    assert not paths.socket_path.exists()
    assert not paths.pid_path.exists()


def test_pid_publication_failure_cleans_bound_socket_without_starting_workers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import signal
    import nuself.daemon.server as server_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    states: list[_UnstartedDaemonState] = []
    publication_error = OSError("pid publication failed")

    class BoundServer:
        def __init__(
            self,
            socket_path: str,
            handler: object,
            state: object,
        ) -> None:
            paths.socket_path.write_text("bound", encoding="utf-8")

        def __enter__(self) -> BoundServer:
            return self

        def __exit__(
            self,
            exc_type: object,
            exc: object,
            traceback: object,
        ) -> None:
            return None

    def make_state(application: object) -> _UnstartedDaemonState:
        state = _UnstartedDaemonState(paths.authority_root)
        states.append(state)
        return state

    def fail_pid_publication(path: Path, content: str) -> None:
        assert path == paths.pid_path
        assert int(content) > 0
        raise publication_error

    def ignore_signal(
        signal_number: int,
        handler: object,
    ) -> object:
        return handler

    monkeypatch.setattr(server_module, "DaemonState", make_state)
    monkeypatch.setattr(server_module, "NuSelfUnixServer", BoundServer)
    monkeypatch.setattr(
        server_module,
        "write_text_atomic",
        fail_pid_publication,
    )
    monkeypatch.setattr(signal, "signal", ignore_signal)

    with pytest.raises(OSError) as captured:
        server_module._run_owned_daemon(paths)

    assert captured.value is publication_error
    assert len(states) == 1
    assert states[0].start_calls == []
    assert states[0].stop_calls == ["scheduler"]
    assert not paths.socket_path.exists()
    assert not paths.pid_path.exists()


def test_owned_daemon_attempts_all_cleanup_and_preserves_primary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import signal
    import nuself.application.lifecycle as runtime_module
    import nuself.daemon.server as server_module
    import nuself.storage.authority as storage_module

    paths = runtime_paths(tmp_path)
    paths.runtime_dir.mkdir(parents=True)
    states: list[_UnstartedDaemonState] = []
    close_roots: list[Path] = []
    backend = storage_module.auto_backend(paths.authority_root)

    class FailingCloseBackend:
        def collection(self, name: str):
            return backend.collection(name)

        def transaction(self):
            return backend.transaction()

        def close(self) -> None:
            close_roots.append(paths.authority_root)
            backend.close()
            raise RuntimeError("storage close failed")

    def make_state(application: object) -> _UnstartedDaemonState:
        state = _UnstartedDaemonState(paths.authority_root)
        state.scheduler.stop_error = RuntimeError("scheduler stop failed")
        states.append(state)
        return state

    def fail_bind(
        socket_path: str,
        handler: object,
        state: object,
    ) -> object:
        raise OSError("bind failed")

    def open_backend(project_root: Path) -> FailingCloseBackend:
        assert project_root == paths.authority_root
        return FailingCloseBackend()

    def ignore_signal(
        signal_number: int,
        handler: object,
    ) -> object:
        return handler

    monkeypatch.setattr(server_module, "DaemonState", make_state)
    monkeypatch.setattr(server_module, "NuSelfUnixServer", fail_bind)
    monkeypatch.setattr(runtime_module, "auto_backend", open_backend)
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
        "scheduler.stop",
        "application_runtime.close",
    ]
    assert states[0].stop_calls == ["scheduler"]
    assert close_roots == [paths.authority_root]
    assert not paths.socket_path.exists()
    assert not paths.pid_path.exists()
    event = read_log_events(
        project_root=tmp_path,
        component="daemon",
    )[-1]
    assert event.event == "shutdown_cleanup_failed"
    assert event.metadata == {
        "failures": (
            {
                "step": "scheduler.stop",
                "error": "scheduler stop failed",
            },
            {
                "step": "application_runtime.close",
                "error": "storage close failed",
            },
        ),
        "primary_failed": True,
    }
    assert event.to_record()["metadata"] == {
        "failures": [
            {
                "step": "scheduler.stop",
                "error": "scheduler stop failed",
            },
            {
                "step": "application_runtime.close",
                "error": "storage close failed",
            },
        ],
        "primary_failed": True,
    }


@pytest.mark.parametrize(
    "release_error",
    [
        OSError("lock release failed"),
        KeyboardInterrupt("lock release interrupted"),
    ],
)
def test_instance_lock_release_failure_retains_owned_daemon_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    release_error: BaseException,
) -> None:
    import nuself.daemon.server as server_module

    class FailingReleaseLock:
        def __init__(self, path: Path) -> None:
            self.path = path

        def acquire(self) -> None:
            return None

        def release(self) -> None:
            raise release_error

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
    assert captured.value.failures[0].error is release_error


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
        pass

    class ImmediateServer:
        def __init__(
            self,
            socket_path: str,
            handler: object,
            state: object,
        ) -> None:
            assert isinstance(state, ExitingState)
            self.state = state
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
            self.state.shutdown_requested.set()

    def make_state(application: object) -> ExitingState:
        state = ExitingState(paths.authority_root)
        states.append(state)
        return state

    def capture_audit(envelope: object, **_kwargs: object) -> object:
        nonlocal stopped_observed
        event = envelope.name  # type: ignore[union-attr]
        if event == "started":
            raise OSError("audit store unavailable")
        if event == "stopped":
            assert states[0].stop_calls == ["scheduler"]
            assert not paths.socket_path.exists()
            assert not paths.pid_path.exists()
            stopped_observed = True
        return object()

    def fail_diagnostic(*_args: object, **_kwargs: object) -> None:
        raise OSError("diagnostic store unavailable")

    def ignore_signal(
        signal_number: int,
        handler: object,
    ) -> object:
        return handler

    monkeypatch.setattr(server_module, "DaemonState", make_state)
    monkeypatch.setattr(server_module, "NuSelfUnixServer", ImmediateServer)
    monkeypatch.setattr(
        "nuself.runtime.observability.write_log_event",
        fail_diagnostic,
    )
    monkeypatch.setattr(
        "nuself.runtime.observability.write_audit_envelope",
        capture_audit,
    )
    monkeypatch.setattr(
        signal,
        "signal",
        ignore_signal,
    )

    with pytest.warns(
        RuntimeWarning,
        match="runtime/observability_sink_failed",
    ):
        server_module._run_owned_daemon(paths)
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

    def make_state(application: object) -> _UnstartedDaemonState:
        return _UnstartedDaemonState(paths.authority_root)

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
