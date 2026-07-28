from __future__ import annotations

from math import isclose
from pathlib import Path
import stat
from typing import BinaryIO, cast

import pytest

from nuself.config import runtime_paths
from nuself.daemon import lifecycle
from nuself.logs import read_log_events
from nuself.private import ensure_private_root


def _no_sleep(seconds: float) -> None:
    del seconds


def test_ensure_private_root_creates_runtime_dirs(tmp_path: Path) -> None:
    paths = ensure_private_root(tmp_path)

    assert paths.private_root.is_dir()
    assert paths.runtime_dir.is_dir()
    assert paths.logs_dir.is_dir()
    assert (tmp_path / "private" / "sources").is_dir()
    assert (tmp_path / "private" / "derived").is_dir()
    assert (tmp_path / "private" / "shares").is_dir()


def test_status_when_daemon_is_missing(tmp_path: Path) -> None:
    status = lifecycle.status(tmp_path)
    paths = runtime_paths(tmp_path)

    assert not status.running
    assert status.pid is None
    assert status.socket_path == paths.socket_path


def test_start_isolates_raw_process_output_from_structured_daemon_log(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = runtime_paths(tmp_path)
    missing = lifecycle.DaemonStatus(
        running=False,
        pid=None,
        socket_path=paths.socket_path,
        pid_path=paths.pid_path,
    )
    running = lifecycle.DaemonStatus(
        running=True,
        pid=42,
        socket_path=paths.socket_path,
        pid_path=paths.pid_path,
    )
    status_calls = 0
    process_logs: list[BinaryIO] = []

    def fake_status(
        project_root: Path | None = None,
        *,
        ping_timeout: float = 2.0,
    ) -> lifecycle.DaemonStatus:
        del project_root, ping_timeout
        nonlocal status_calls
        status_calls += 1
        return missing if status_calls == 1 else running

    def fake_popen(
        args: object,
        **kwargs: object,
    ) -> object:
        process_log = cast(BinaryIO, kwargs["stdout"])
        assert process_log.closed is False
        process_log.write(b"raw daemon stderr\n")
        process_log.flush()
        process_logs.append(process_log)
        return object()

    monkeypatch.setattr(lifecycle, "status", fake_status)
    monkeypatch.setattr(lifecycle.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(lifecycle.time, "sleep", _no_sleep)

    assert lifecycle.start(tmp_path) == running

    assert process_logs[0].closed is True
    assert (
        paths.daemon_process_log_path.read_text(encoding="utf-8")
        == "raw daemon stderr\n"
    )
    assert not paths.daemon_log_path.exists()
    assert read_log_events(project_root=tmp_path, component="daemon") == []


def test_start_rotates_bounded_raw_process_log_before_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = runtime_paths(tmp_path)
    paths.logs_dir.mkdir(parents=True)
    for path, content in (
        (paths.daemon_process_log_path, "active-old"),
        (paths.daemon_process_log_path.with_name("daemon-process.log.1"), "one"),
        (paths.daemon_process_log_path.with_name("daemon-process.log.2"), "two"),
        (paths.daemon_process_log_path.with_name("daemon-process.log.3"), "three"),
    ):
        path.write_text(content, encoding="utf-8")
        path.chmod(0o644)
    missing = lifecycle.DaemonStatus(
        running=False,
        pid=None,
        socket_path=paths.socket_path,
        pid_path=paths.pid_path,
    )
    running = lifecycle.DaemonStatus(
        running=True,
        pid=42,
        socket_path=paths.socket_path,
        pid_path=paths.pid_path,
    )
    status_calls = 0

    def fake_status(
        project_root: Path | None = None,
        *,
        ping_timeout: float = 2.0,
    ) -> lifecycle.DaemonStatus:
        del project_root, ping_timeout
        nonlocal status_calls
        status_calls += 1
        return missing if status_calls == 1 else running

    def fake_popen(args: object, **kwargs: object) -> object:
        assert (
            paths.daemon_process_log_path.with_name(
                "daemon-process.log.1"
            ).read_text(encoding="utf-8")
            == "active-old"
        )
        process_log = cast(BinaryIO, kwargs["stdout"])
        process_log.write(b"active-new")
        process_log.flush()
        return object()

    monkeypatch.setattr(lifecycle, "status", fake_status)
    monkeypatch.setattr(lifecycle.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(lifecycle.time, "sleep", _no_sleep)

    lifecycle.start(
        tmp_path,
        process_log_retention=lifecycle.DaemonProcessLogRetentionPolicy(
            max_bytes=1,
            backup_count=3,
        ),
    )

    assert paths.daemon_process_log_path.read_text(encoding="utf-8") == "active-new"
    assert (
        paths.daemon_process_log_path.with_name(
            "daemon-process.log.1"
        ).read_text(encoding="utf-8")
        == "active-old"
    )
    assert (
        paths.daemon_process_log_path.with_name(
            "daemon-process.log.2"
        ).read_text(encoding="utf-8")
        == "one"
    )
    assert (
        paths.daemon_process_log_path.with_name(
            "daemon-process.log.3"
        ).read_text(encoding="utf-8")
        == "two"
    )
    for path in paths.logs_dir.glob("daemon-process.log*"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_process_log_rotation_failure_warns_safely_and_continues_start(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = runtime_paths(tmp_path)
    missing = lifecycle.DaemonStatus(
        running=False,
        pid=None,
        socket_path=paths.socket_path,
        pid_path=paths.pid_path,
    )
    running = lifecycle.DaemonStatus(
        running=True,
        pid=42,
        socket_path=paths.socket_path,
        pid_path=paths.pid_path,
    )
    status_calls = 0
    spawned = False
    private_path = tmp_path / "private rotation target"

    def fake_status(
        project_root: Path | None = None,
        *,
        ping_timeout: float = 2.0,
    ) -> lifecycle.DaemonStatus:
        del project_root, ping_timeout
        nonlocal status_calls
        status_calls += 1
        return missing if status_calls == 1 else running

    def fail_rotation(
        path: Path,
        policy: lifecycle.DaemonProcessLogRetentionPolicy,
    ) -> None:
        raise PermissionError(13, "private rotation failure", private_path)

    def fake_popen(args: object, **kwargs: object) -> object:
        nonlocal spawned
        spawned = True
        return object()

    monkeypatch.setattr(lifecycle, "status", fake_status)
    monkeypatch.setattr(
        lifecycle,
        "_rotate_daemon_process_log_if_needed",
        fail_rotation,
    )
    monkeypatch.setattr(lifecycle.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(lifecycle.time, "sleep", _no_sleep)

    with pytest.warns(RuntimeWarning) as captured:
        assert lifecycle.start(tmp_path) == running

    assert spawned is True
    warning = str(captured[0].message)
    assert "process_log_rotation_failed" in warning
    assert "error_type=PermissionError" in warning
    assert "private rotation failure" not in warning
    assert str(private_path) not in warning


@pytest.mark.parametrize(
    ("max_bytes", "backup_count"),
    [(0, 1), (1, 0)],
)
def test_process_log_retention_policy_rejects_unbounded_values(
    max_bytes: int,
    backup_count: int,
) -> None:
    with pytest.raises(ValueError):
        lifecycle.DaemonProcessLogRetentionPolicy(
            max_bytes=max_bytes,
            backup_count=backup_count,
        )


@pytest.mark.parametrize(
    ("timeout_seconds", "poll_interval_seconds"),
    [
        (0, 0.05),
        (float("inf"), 0.05),
        (float("nan"), 0.05),
        (True, 0.05),
        (2, 0),
        (2, float("inf")),
        (2, float("nan")),
        (2, True),
    ],
)
def test_startup_policy_rejects_invalid_timing(
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> None:
    with pytest.raises(ValueError):
        lifecycle.DaemonStartupPolicy(
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )


def test_start_wraps_spawn_failure_and_preserves_cause(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopped = lifecycle.DaemonStatus(
        running=False,
        pid=None,
        socket_path=runtime_paths(tmp_path).socket_path,
        pid_path=runtime_paths(tmp_path).pid_path,
    )
    failure = PermissionError("private spawn detail")

    def stopped_status(
        project_root: Path | None = None,
        *,
        ping_timeout: float = 2.0,
    ) -> lifecycle.DaemonStatus:
        del project_root, ping_timeout
        return stopped

    monkeypatch.setattr(lifecycle, "status", stopped_status)

    def fail_spawn(args: object, **kwargs: object) -> object:
        raise failure

    monkeypatch.setattr(lifecycle.subprocess, "Popen", fail_spawn)

    with pytest.raises(lifecycle.DaemonStartError) as captured:
        lifecycle.start(tmp_path)

    error = captured.value
    assert error.reason == "spawn_failed"
    assert error.status is stopped
    assert error.exit_code is None
    assert error.__cause__ is failure
    assert str(error) == "daemon process could not be spawned"
    assert "private spawn detail" not in str(error)


def test_start_reports_child_exit_before_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = runtime_paths(tmp_path)
    stopped = lifecycle.DaemonStatus(
        running=False,
        pid=None,
        socket_path=paths.socket_path,
        pid_path=paths.pid_path,
    )

    class ExitedProcess:
        def poll(self) -> int:
            return 23

    def stopped_status(
        project_root: Path | None = None,
        *,
        ping_timeout: float = 2.0,
    ) -> lifecycle.DaemonStatus:
        del project_root, ping_timeout
        return stopped

    def spawn_exited_process(
        args: object,
        **kwargs: object,
    ) -> ExitedProcess:
        del args, kwargs
        return ExitedProcess()

    monkeypatch.setattr(lifecycle, "status", stopped_status)
    monkeypatch.setattr(
        lifecycle.subprocess,
        "Popen",
        spawn_exited_process,
    )

    with pytest.raises(lifecycle.DaemonStartError) as captured:
        lifecycle.start(tmp_path)

    error = captured.value
    assert error.reason == "process_exited"
    assert error.status is stopped
    assert error.exit_code == 23
    assert str(error) == (
        "daemon process exited before becoming ready (exit_code=23)"
    )


def test_start_uses_monotonic_deadline_without_oversleep(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = runtime_paths(tmp_path)
    stopped = lifecycle.DaemonStatus(
        running=False,
        pid=None,
        socket_path=paths.socket_path,
        pid_path=paths.pid_path,
    )
    now = 100.0
    sleeps: list[float] = []
    ping_timeouts: list[float] = []

    class LiveProcess:
        def poll(self) -> None:
            return None

    def stopped_status(
        project_root: Path | None = None,
        *,
        ping_timeout: float = 2.0,
    ) -> lifecycle.DaemonStatus:
        del project_root
        ping_timeouts.append(ping_timeout)
        return stopped

    def spawn_live_process(
        args: object,
        **kwargs: object,
    ) -> LiveProcess:
        del args, kwargs
        return LiveProcess()

    def monotonic() -> float:
        return now

    def sleep(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    monkeypatch.setattr(lifecycle, "status", stopped_status)
    monkeypatch.setattr(
        lifecycle.subprocess,
        "Popen",
        spawn_live_process,
    )
    monkeypatch.setattr(lifecycle.time, "monotonic", monotonic)
    monkeypatch.setattr(lifecycle.time, "sleep", sleep)

    with pytest.raises(lifecycle.DaemonStartError) as captured:
        lifecycle.start(
            tmp_path,
            startup_policy=lifecycle.DaemonStartupPolicy(
                timeout_seconds=0.12,
                poll_interval_seconds=0.05,
            ),
        )

    error = captured.value
    assert error.reason == "timeout"
    assert error.status is stopped
    assert error.timeout_seconds == 0.12
    assert isclose(sum(sleeps), 0.12)
    assert len(sleeps) == 3
    assert all(
        isclose(actual, expected)
        for actual, expected in zip(sleeps, [0.05, 0.05, 0.02], strict=True)
    )
    assert ping_timeouts[0] == 2.0
    assert all(
        timeout > 0 and (timeout < 0.12 or isclose(timeout, 0.12))
        for timeout in ping_timeouts[1:]
    )
    assert str(error) == "daemon did not become ready within 0.12 seconds"


def test_read_pid_missing_file_returns_none(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    assert lifecycle.read_pid(paths) is None


def test_read_pid_empty_file_returns_none(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    paths.pid_path.parent.mkdir(parents=True, exist_ok=True)
    paths.pid_path.write_text("", encoding="utf-8")
    assert lifecycle.read_pid(paths) is None
    event = read_log_events(project_root=tmp_path, component="daemon")[-1]
    assert event.event == "record_decode_failed"
    assert event.metadata == {
        "collection": "daemon_runtime",
        "record_id": "nuself",
    }
    assert event.error == "daemon PID metadata is invalid"


@pytest.mark.parametrize(
    "raw_pid",
    ["", "not-a-pid", "+1", "1.0", "１２"],
)
def test_read_pid_invalid_value_returns_none(
    tmp_path: Path,
    raw_pid: str,
) -> None:
    paths = runtime_paths(tmp_path)
    paths.pid_path.parent.mkdir(parents=True, exist_ok=True)
    paths.pid_path.write_text(raw_pid, encoding="utf-8")
    assert lifecycle.read_pid(paths) is None
    event = read_log_events(project_root=tmp_path, component="daemon")[-1]
    if raw_pid:
        assert raw_pid not in (event.error or "")


@pytest.mark.parametrize("raw_pid", ["0", "-1"])
def test_read_pid_non_positive_value_is_corrupt(
    tmp_path: Path,
    raw_pid: str,
) -> None:
    paths = runtime_paths(tmp_path)
    paths.pid_path.parent.mkdir(parents=True, exist_ok=True)
    paths.pid_path.write_text(raw_pid, encoding="utf-8")

    assert lifecycle.read_pid(paths) is None
    event = read_log_events(project_root=tmp_path, component="daemon")[-1]
    assert event.event == "record_decode_failed"


def test_read_pid_valid_value_returns_int(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    paths.pid_path.parent.mkdir(parents=True, exist_ok=True)
    paths.pid_path.write_text(" \n12345\t", encoding="utf-8")
    assert lifecycle.read_pid(paths) == 12345


def test_read_pid_non_missing_io_failure_propagates(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    paths.pid_path.mkdir(parents=True)

    with pytest.raises(IsADirectoryError):
        lifecycle.read_pid(paths)
