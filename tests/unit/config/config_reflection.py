"""Tests for reflection configuration through unified ConfigSystem."""

from __future__ import annotations

from pathlib import Path

import pytest

from nuself.config import ConfigSystem


def test_reflection_settings_default_loaded_from_system(tmp_path: Path) -> None:
    config = ConfigSystem.load(project_root=tmp_path)
    assert config.reflection.scheduler.interval_seconds >= 60
    assert config.reflection.scheduler.daily_cap >= 1
    assert 0.0 <= config.reflection.gate.relevance_threshold <= 1.0
    assert 0.0 <= config.reflection.gate.persona_discussion_threshold <= 1.0
    assert config.reflection.moderator.max_discussion_rounds >= 1


def test_reflection_settings_from_yaml(tmp_path: Path) -> None:
    private_dir = tmp_path
    private_dir.mkdir(parents=True, exist_ok=True)
    (private_dir / "config.yaml").write_text(
        """
reflection:
  scheduler:
    interval_seconds: 600
  gate:
    relevance_threshold: 0.3
""",
        encoding="utf-8",
    )

    config = ConfigSystem.load(project_root=tmp_path)
    assert config.reflection.scheduler.interval_seconds == 600
    assert config.reflection.gate.relevance_threshold == 0.3
    assert config.reflection.scheduler.daily_cap == 5


def test_language_preference_default_is_en(tmp_path: Path) -> None:
    config = ConfigSystem.load(project_root=tmp_path)
    assert config.chat.language_preference == "en"


def test_language_preference_from_yaml(tmp_path: Path) -> None:
    private_dir = tmp_path
    private_dir.mkdir(parents=True, exist_ok=True)
    (private_dir / "config.yaml").write_text(
        "chat:\n  language_preference: zh-CN\n",
        encoding="utf-8",
    )

    config = ConfigSystem.load(project_root=tmp_path)
    assert config.chat.language_preference == "zh-CN"


def test_llm_endpoint_list_from_yaml(tmp_path: Path) -> None:
    private_dir = tmp_path
    private_dir.mkdir(parents=True, exist_ok=True)
    (private_dir / "config.yaml").write_text(
        """
llm:
  - base_url: https://primary.example/v1
    api_key: primary-key
    model: primary-model
  - anthropic: true
    api_key: anthropic-key
    model: claude-model
""",
        encoding="utf-8",
    )

    config = ConfigSystem.load(project_root=tmp_path)

    assert len(config.llm.endpoints) == 2
    assert config.llm.endpoints[0].base_url == "https://primary.example/v1"
    assert config.llm.endpoints[1].model == "claude-model"
    assert config.llm.endpoints[1].anthropic is True
    assert config.llm.endpoints[1].base_url == "https://api.anthropic.com"
    assert ConfigSystem.as_flat_dict(config)["llm.count"] == 2


def test_llm_endpoint_timeout_and_chat_request_timeout_from_yaml(tmp_path: Path) -> None:
    private_dir = tmp_path
    private_dir.mkdir(parents=True, exist_ok=True)
    (private_dir / "config.yaml").write_text(
        """
llm:
  - base_url: http://localhost:11434/v1
    api_key: ollama
    model: deepseek-r1
    timeout_seconds: 300
chat:
  request_timeout_seconds: 600
""",
        encoding="utf-8",
    )

    config = ConfigSystem.load(project_root=tmp_path)

    assert config.llm.endpoints[0].timeout_seconds == 300
    assert config.chat.request_timeout_seconds == 600
    assert ConfigSystem.as_flat_dict(config)["chat.request_timeout_seconds"] == 600


def test_llm_nested_openai_object_is_rejected(tmp_path: Path) -> None:
    private_dir = tmp_path
    private_dir.mkdir(parents=True, exist_ok=True)
    (private_dir / "config.yaml").write_text(
        """
llm:
  openai:
    base_url: https://primary.example/v1
    api_key: primary-key
    model: primary-model
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="endpoint list"):
        ConfigSystem.load(project_root=tmp_path)
