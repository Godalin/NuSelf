"""Tests for LLM JSON parsing helpers."""

from __future__ import annotations

import pytest

from nuself.llm import parse_llm_json_object


def test_parse_llm_json_object_accepts_plain_json() -> None:
    assert parse_llm_json_object('{"answer": "ok"}') == {"answer": "ok"}


def test_parse_llm_json_object_strips_markdown_fences() -> None:
    assert parse_llm_json_object('```json\n{"answer": "ok"}\n```') == {"answer": "ok"}


def test_parse_llm_json_object_rejects_non_object_json() -> None:
    with pytest.raises(ValueError):
        parse_llm_json_object('["not", "object"]')
