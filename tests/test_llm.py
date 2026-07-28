"""Tests for LLM JSON parsing helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from nuself.llm import LLMSettings, parse_llm_json_object


def test_parse_llm_json_object_accepts_plain_json() -> None:
    assert parse_llm_json_object('{"answer": "ok"}') == {"answer": "ok"}


def test_parse_llm_json_object_strips_markdown_fences() -> None:
    assert parse_llm_json_object('```json\n{"answer": "ok"}\n```') == {"answer": "ok"}


def test_parse_llm_json_object_rejects_non_object_json() -> None:
    with pytest.raises(ValueError):
        parse_llm_json_object('["not", "object"]')


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
