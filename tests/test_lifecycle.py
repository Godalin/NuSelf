from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, cast

import pytest

from nuself.config import runtime_paths
from nuself.daemon import lifecycle
from nuself.logs import read_log_events
from nuself.private import ensure_private_root


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

    def no_sleep(seconds: float) -> None:
        del seconds

    monkeypatch.setattr(lifecycle, "status", fake_status)
    monkeypatch.setattr(lifecycle.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(lifecycle.time, "sleep", no_sleep)

    assert lifecycle.start(tmp_path) == running

    assert process_logs[0].closed is True
    assert (
        paths.daemon_process_log_path.read_text(encoding="utf-8")
        == "raw daemon stderr\n"
    )
    assert not paths.daemon_log_path.exists()
    assert read_log_events(project_root=tmp_path, component="daemon") == []


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
