# pyright: reportPrivateUsage=false
"""Daemon cross-process instance ownership tests."""

from __future__ import annotations

from pathlib import Path
import threading

import pytest

from nuself.config import runtime_paths
from nuself.daemon.instance import (
    DaemonInstanceLock,
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
