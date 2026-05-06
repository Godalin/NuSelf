from __future__ import annotations

from pathlib import Path

from nuself.config import runtime_paths
from nuself.daemon import lifecycle
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

