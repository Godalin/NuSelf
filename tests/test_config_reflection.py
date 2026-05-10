"""Tests for reflection configuration system."""

from __future__ import annotations

from pathlib import Path
import tempfile

from nuself.config_reflection import ReflectionConfig


def test_reflection_config_default() -> None:
    """Test that default config is safe and reasonable."""
    config = ReflectionConfig.default()
    assert config.interval_seconds >= 60
    assert config.daily_cap >= 1
    assert 0.0 <= config.relevance_threshold <= 1.0
    assert 0.0 <= config.persona_discussion_threshold <= 1.0
    assert config.max_discussion_rounds >= 1


def test_reflection_config_from_yaml_missing_file() -> None:
    """Test that missing config file returns defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "nonexistent.yaml"
        config = ReflectionConfig.from_yaml(config_path)
        assert config.interval_seconds >= 60
        assert config.daily_cap >= 1


def test_reflection_config_from_yaml_empty_file() -> None:
    """Test that empty YAML file returns defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "empty.yaml"
        config_path.write_text("")
        config = ReflectionConfig.from_yaml(config_path)
        assert config.interval_seconds >= 60
        assert config.daily_cap >= 1


def test_reflection_config_from_yaml_partial_config() -> None:
    """Test that partial config merges with defaults."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "partial.yaml"
        config_path.write_text("""
scheduler:
  interval_seconds: 600
gate:
  relevance_threshold: 0.3
""")
        config = ReflectionConfig.from_yaml(config_path)
        assert config.interval_seconds == 600
        assert config.relevance_threshold == 0.3
        assert config.daily_cap == 5  # default


def test_reflection_config_clamping() -> None:
    """Test that config values are properly clamped to safe ranges."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "invalid.yaml"
        config_path.write_text("""
scheduler:
  interval_seconds: 10
  quiet_start_hour: 30
  quiet_end_hour: -5
  daily_cap: 0
  jitter_percent: 100
gate:
  relevance_threshold: 1.5
  persona_discussion_threshold: -0.5
moderator:
  max_discussion_rounds: 0
  moderator_convergence_patience: 0
""")
        config = ReflectionConfig.from_yaml(config_path)
        assert config.interval_seconds == 60  # clamped to minimum
        assert config.quiet_start_hour == 23  # clamped to 0-23
        assert config.quiet_end_hour == 0  # clamped to 0-23
        assert config.daily_cap == 1  # clamped to minimum
        assert config.jitter_percent == 50  # clamped to maximum
        assert config.relevance_threshold == 1.0  # clamped to 0-1
        assert config.persona_discussion_threshold == 0.0  # clamped to 0-1
        assert config.max_discussion_rounds == 1  # clamped to minimum
        assert config.moderator_convergence_patience == 1  # clamped to minimum


def test_reflection_config_for_testing() -> None:
    """Test that fast testing config disables most features."""
    config = ReflectionConfig.for_testing(interval_seconds=5, daily_cap=50)
    assert config.interval_seconds == 5
    assert config.daily_cap == 50
    assert config.cooldown_seconds == 0
    assert config.jitter_percent == 0
    assert config.relevance_threshold == 0.0
    assert config.persona_discussion_threshold == 1.0  # high, effectively disables discussion
