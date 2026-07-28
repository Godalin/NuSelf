from __future__ import annotations

from pathlib import Path

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
