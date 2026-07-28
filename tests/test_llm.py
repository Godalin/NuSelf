"""Tests for LLM configuration and adapters."""

from __future__ import annotations

from pathlib import Path

from nuself.llm import LLMSettings


def test_llm_settings_preserve_configured_timeout(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir()
    (private / "config.yaml").write_text(
        "llm:\n"
        "  - base_url: https://example.invalid/v1\n"
        "    api_key: test\n"
        "    model: demo\n"
        "    timeout_seconds: 17\n",
        encoding="utf-8",
    )
    assert LLMSettings.from_project(tmp_path).timeout_seconds == 17
