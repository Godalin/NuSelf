from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from nuself.config import find_project_root, runtime_paths


def test_runtime_paths_are_under_private_root(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    assert paths.private_root == tmp_path / "private"
    assert paths.runtime_dir == tmp_path / "private" / "runtime"
    assert paths.logs_dir == tmp_path / "private" / "logs"
    assert paths.socket_path == tmp_path / "private" / "runtime" / "nuself.sock"

    with pytest.raises(FrozenInstanceError):
        setattr(paths, "private_root", tmp_path)


def test_find_project_root_finds_agents_md(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    assert find_project_root(tmp_path) == tmp_path


def test_find_project_root_fallback_to_cwd_when_no_agents_md(tmp_path: Path) -> None:
    result = find_project_root(tmp_path)
    assert result == tmp_path
