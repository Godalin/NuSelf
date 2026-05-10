"""Configuration system for the reflection scheduler and proactive persona discussion.

Configuration is stored in a YAML file at private/reflection_config.yaml.
Environment variables can override YAML settings for testing and deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml


@dataclass(frozen=True)
class ReflectionConfig:
    """Configuration for reflection scheduling and persona discussion policies.
    
    All parameters are clamped to safe ranges to prevent misconfigurations.
    """

    # Scheduler parameters
    interval_seconds: int  # Base interval between reflection cycles (minimum 60)
    cooldown_seconds: int  # Minimum time after last reflection before attempting again
    quiet_start_hour: int  # Start of quiet hours (0-23)
    quiet_end_hour: int  # End of quiet hours (0-23)
    daily_cap: int  # Maximum reflections per day (minimum 1)
    jitter_percent: int  # Random jitter on interval (0-50%)
    
    # Relevance gate parameters
    relevance_threshold: float  # Minimum composite score to pass (0.0-1.0)
    persona_discussion_threshold: float  # Score threshold to trigger persona discussion (0.0-1.0)
    
    # Moderator parameters
    max_discussion_rounds: int  # Maximum rounds in persona discussion
    moderator_convergence_patience: int  # Rounds to try before forcing conclusion
    
    @classmethod
    def from_yaml(cls, config_path: Path | None = None) -> ReflectionConfig:
        """Load configuration from YAML file, with safe defaults."""
        if config_path is None:
            from nuself.config import find_project_root
            project_root = find_project_root()
            config_path = project_root / "private" / "reflection_config.yaml"
        
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                raw_data: Any = yaml.safe_load(f)  # type: ignore[no-untyped-call]
                data = cast(dict[str, object], raw_data if isinstance(raw_data, dict) else {})
        except FileNotFoundError:
            # Return defaults if file doesn't exist
            return cls.default()
        except Exception:
            # Return defaults on any YAML parsing error
            return cls.default()
        
        # Extract sections with type safety
        scheduler: dict[str, object] = {}
        gate: dict[str, object] = {}
        moderator: dict[str, object] = {}
        
        if isinstance(data.get("scheduler"), dict):
            scheduler = data["scheduler"]  # type: ignore[assignment]
        if isinstance(data.get("gate"), dict):
            gate = data["gate"]  # type: ignore[assignment]
        if isinstance(data.get("moderator"), dict):
            moderator = data["moderator"]  # type: ignore[assignment]
        
        # Safe getter with type coercion
        def get_int(d: dict[str, object], key: str, default: int) -> int:
            val = d.get(key)
            if isinstance(val, int):
                return val
            if isinstance(val, str):
                try:
                    return int(val)
                except ValueError:
                    return default
            return default
        
        def get_float(d: dict[str, object], key: str, default: float) -> float:
            val = d.get(key)
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val)
                except ValueError:
                    return default
            return default
        
        # Apply values with clamping
        return cls(
            interval_seconds=max(get_int(scheduler, "interval_seconds", 3600), 60),
            cooldown_seconds=max(get_int(scheduler, "cooldown_seconds", 300), 0),
            quiet_start_hour=max(0, min(get_int(scheduler, "quiet_start_hour", 22), 23)),
            quiet_end_hour=max(0, min(get_int(scheduler, "quiet_end_hour", 7), 23)),
            daily_cap=max(get_int(scheduler, "daily_cap", 5), 1),
            jitter_percent=max(0, min(get_int(scheduler, "jitter_percent", 20), 50)),
            relevance_threshold=max(0.0, min(get_float(gate, "relevance_threshold", 0.5), 1.0)),
            persona_discussion_threshold=max(0.0, min(get_float(gate, "persona_discussion_threshold", 0.7), 1.0)),
            max_discussion_rounds=max(get_int(moderator, "max_discussion_rounds", 10), 1),
            moderator_convergence_patience=max(get_int(moderator, "moderator_convergence_patience", 5), 1),
        )
    
    @classmethod
    def default(cls) -> ReflectionConfig:
        """Return a safe default configuration."""
        return cls(
            interval_seconds=3600,
            cooldown_seconds=300,
            quiet_start_hour=22,
            quiet_end_hour=7,
            daily_cap=5,
            jitter_percent=20,
            relevance_threshold=0.5,
            persona_discussion_threshold=0.55,
            max_discussion_rounds=10,
            moderator_convergence_patience=5,
        )
    
    @classmethod
    def for_testing(cls, interval_seconds: int = 10, daily_cap: int = 100) -> ReflectionConfig:
        """Return a configuration suitable for fast testing."""
        return cls(
            interval_seconds=max(interval_seconds, 1),
            cooldown_seconds=0,
            quiet_start_hour=1,  # Narrow quiet window (1-2) that won't affect typical test times
            quiet_end_hour=2,
            daily_cap=daily_cap,
            jitter_percent=0,
            relevance_threshold=0.0,
            persona_discussion_threshold=1.0,  # Disable persona discussion by default in tests
            max_discussion_rounds=2,
            moderator_convergence_patience=1,
        )
