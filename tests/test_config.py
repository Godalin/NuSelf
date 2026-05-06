from __future__ import annotations

from pathlib import Path

from nuself.config import config_int, config_value, load_project_env


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
