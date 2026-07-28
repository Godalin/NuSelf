from __future__ import annotations

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

    def fake_status(project_root: Path | None = None) -> lifecycle.DaemonStatus:
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

    def fake_status(project_root: Path | None = None) -> lifecycle.DaemonStatus:
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

    def fake_status(project_root: Path | None = None) -> lifecycle.DaemonStatus:
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
