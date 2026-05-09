from __future__ import annotations

from pathlib import Path

from nuself.config import config_int, config_value, find_project_root, load_project_env


def test_project_env_loader_reads_simple_assignments(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "# local config",
                "OPENAI_MODEL='example-model'",
                'OPENAI_BASE_URL="https://example.test/v1"',
                "NUSELF_CONTEXT_RECENT_MESSAGES=8",
            ]
        ),
        encoding="utf-8",
    )

    env = load_project_env(tmp_path)

    assert env["OPENAI_MODEL"] == "example-model"
    assert config_value("OPENAI_BASE_URL", "", tmp_path) == "https://example.test/v1"
    assert config_int("NUSELF_CONTEXT_RECENT_MESSAGES", 12, tmp_path) == 8


def test_load_project_env_missing_file_returns_empty(tmp_path: Path) -> None:
    env = load_project_env(tmp_path)
    assert env == {}


def test_config_int_invalid_value_returns_default(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("INVALID_NUMBER=not-an-int\n", encoding="utf-8")
    assert config_int("INVALID_NUMBER", 42, tmp_path) == 42


def test_config_int_non_positive_returns_default(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("NEGATIVE=-5\n", encoding="utf-8")
    assert config_int("NEGATIVE", 42, tmp_path) == 42

    (tmp_path / ".env").write_text("ZERO=0\n", encoding="utf-8")
    assert config_int("ZERO", 42, tmp_path) == 42


def test_find_project_root_finds_agents_md(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Agents\n", encoding="utf-8")
    assert find_project_root(tmp_path) == tmp_path


def test_find_project_root_fallback_to_cwd_when_no_agents_md(tmp_path: Path) -> None:
    result = find_project_root(tmp_path)
    assert result == tmp_path
