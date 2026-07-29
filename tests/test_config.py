from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from nuself.config import ConfigSystem, find_project_root, runtime_paths


def test_runtime_paths_are_under_private_root(tmp_path: Path) -> None:
    paths = runtime_paths(tmp_path)
    assert paths.private_root == tmp_path / "private"
    assert paths.runtime_dir == tmp_path / "private" / "runtime"
    assert paths.logs_dir == tmp_path / "private" / "logs"
    assert paths.socket_path == tmp_path / "private" / "runtime" / "nuself.sock"
    assert paths.daemon_lock_path == tmp_path / "private" / "runtime" / "nuself.lock"
    assert (
        paths.daemon_process_log_path
        == tmp_path / "private" / "logs" / "daemon-process.log"
    )

    with pytest.raises(FrozenInstanceError):
        setattr(paths, "private_root", tmp_path)


def test_find_project_root_finds_agents_md(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    assert find_project_root(tmp_path) == tmp_path


def test_find_project_root_fallback_to_cwd_when_no_agents_md(tmp_path: Path) -> None:
    result = find_project_root(tmp_path)
    assert result == tmp_path


def test_flat_config_redacts_every_endpoint_key_without_aggregate_values(
    tmp_path: Path,
) -> None:
    secret_one = "first-provider-secret"
    secret_two = "second-provider-secret"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        (
            "llm:\n"
            "  - base_url: https://one.example/v1\n"
            f"    api_key: {secret_one}\n"
            "    model: first\n"
            "  - base_url: https://two.example/v1\n"
            f"    api_key: {secret_two}\n"
            "    model: second\n"
        ),
        encoding="utf-8",
    )

    config = ConfigSystem.load(config_path, tmp_path)
    flat = ConfigSystem().as_flat_dict(config)
    rendered = repr(flat)

    assert secret_one not in rendered
    assert secret_two not in rendered
    assert flat["llm.endpoints.0.api_key"] == "***"
    assert flat["llm.endpoints.1.api_key"] == "***"
    assert not any(
        isinstance(value, (dict, list, tuple))
        for value in flat.values()
    )
