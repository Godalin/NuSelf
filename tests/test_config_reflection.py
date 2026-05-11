"""Tests for reflection configuration through unified ConfigSystem."""

from __future__ import annotations

from pathlib import Path

from nuself.config_system import ConfigSystem


def test_reflection_settings_default_loaded_from_system(tmp_path: Path) -> None:
    config = ConfigSystem.load(project_root=tmp_path)
    assert config.reflection.scheduler.interval_seconds >= 60
    assert config.reflection.scheduler.daily_cap >= 1
    assert 0.0 <= config.reflection.gate.relevance_threshold <= 1.0
    assert 0.0 <= config.reflection.gate.persona_discussion_threshold <= 1.0
    assert config.reflection.moderator.max_discussion_rounds >= 1


def test_reflection_settings_from_yaml(tmp_path: Path) -> None:
    private_dir = tmp_path / "private"
    private_dir.mkdir(parents=True)
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
