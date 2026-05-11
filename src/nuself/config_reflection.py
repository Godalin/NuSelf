"""Configuration system for the reflection scheduler and proactive persona discussion.

Configuration is stored in a YAML file at private/reflection_config.yaml.
Environment variables can override YAML settings for testing and deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
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

    @staticmethod
    def _default_values() -> dict[str, int | float]:
        return {
            "interval_seconds": 3600,
            "cooldown_seconds": 300,
            "quiet_start_hour": 22,
            "quiet_end_hour": 7,
            "daily_cap": 5,
            "jitter_percent": 20,
            "relevance_threshold": 0.5,
            "persona_discussion_threshold": 0.55,
            "max_discussion_rounds": 10,
            "moderator_convergence_patience": 5,
        }
    
    @classmethod
    def from_yaml(cls, config_path: Path | None = None) -> ReflectionConfig:
        """Load config from YAML with environment overrides and safe defaults."""
        if config_path is None:
            from nuself.config import find_project_root
            project_root = find_project_root()
            config_path = project_root / "private" / "reflection_config.yaml"

        defaults = cls._default_values()
        
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

        def env_int(name: str, fallback: int) -> int:
            raw = os.environ.get(name)
            if raw is None:
                return fallback
            try:
                return int(raw)
            except ValueError:
                return fallback

        def env_float(name: str, fallback: float) -> float:
            raw = os.environ.get(name)
            if raw is None:
                return fallback
            try:
                return float(raw)
            except ValueError:
                return fallback

        interval_seconds = env_int(
            "NUSELF_REFLECTION_INTERVAL_SECONDS",
            get_int(scheduler, "interval_seconds", int(defaults["interval_seconds"])),
        )
        cooldown_seconds = env_int(
            "NUSELF_REFLECTION_COOLDOWN_SECONDS",
            get_int(scheduler, "cooldown_seconds", int(defaults["cooldown_seconds"])),
        )
        quiet_start_hour = env_int(
            "NUSELF_REFLECTION_QUIET_START_HOUR",
            get_int(scheduler, "quiet_start_hour", int(defaults["quiet_start_hour"])),
        )
        quiet_end_hour = env_int(
            "NUSELF_REFLECTION_QUIET_END_HOUR",
            get_int(scheduler, "quiet_end_hour", int(defaults["quiet_end_hour"])),
        )
        daily_cap = env_int(
            "NUSELF_REFLECTION_DAILY_CAP",
            get_int(scheduler, "daily_cap", int(defaults["daily_cap"])),
        )
        jitter_percent = env_int(
            "NUSELF_REFLECTION_JITTER_PERCENT",
            get_int(scheduler, "jitter_percent", int(defaults["jitter_percent"])),
        )
        relevance_threshold = env_float(
            "NUSELF_REFLECTION_RELEVANCE_THRESHOLD",
            get_float(gate, "relevance_threshold", float(defaults["relevance_threshold"])),
        )
        persona_discussion_threshold = env_float(
            "NUSELF_REFLECTION_PERSONA_DISCUSSION_THRESHOLD",
            get_float(gate, "persona_discussion_threshold", float(defaults["persona_discussion_threshold"])),
        )
        max_discussion_rounds = env_int(
            "NUSELF_REFLECTION_MAX_DISCUSSION_ROUNDS",
            get_int(moderator, "max_discussion_rounds", int(defaults["max_discussion_rounds"])),
        )
        moderator_convergence_patience = env_int(
            "NUSELF_REFLECTION_MODERATOR_CONVERGENCE_PATIENCE",
            get_int(
                moderator,
                "moderator_convergence_patience",
                int(defaults["moderator_convergence_patience"]),
            ),
        )
        
        # Apply values with clamping
        return cls(
            interval_seconds=max(interval_seconds, 60),
            cooldown_seconds=max(cooldown_seconds, 0),
            quiet_start_hour=max(0, min(quiet_start_hour, 23)),
            quiet_end_hour=max(0, min(quiet_end_hour, 23)),
            daily_cap=max(daily_cap, 1),
            jitter_percent=max(0, min(jitter_percent, 50)),
            relevance_threshold=max(0.0, min(relevance_threshold, 1.0)),
            persona_discussion_threshold=max(0.0, min(persona_discussion_threshold, 1.0)),
            max_discussion_rounds=max(max_discussion_rounds, 1),
            moderator_convergence_patience=max(moderator_convergence_patience, 1),
        )
    
    @classmethod
    def default(cls) -> ReflectionConfig:
        """Return a safe default configuration."""
        defaults = cls._default_values()
        return cls(
            interval_seconds=int(defaults["interval_seconds"]),
            cooldown_seconds=int(defaults["cooldown_seconds"]),
            quiet_start_hour=int(defaults["quiet_start_hour"]),
            quiet_end_hour=int(defaults["quiet_end_hour"]),
            daily_cap=int(defaults["daily_cap"]),
            jitter_percent=int(defaults["jitter_percent"]),
            relevance_threshold=float(defaults["relevance_threshold"]),
            persona_discussion_threshold=float(defaults["persona_discussion_threshold"]),
            max_discussion_rounds=int(defaults["max_discussion_rounds"]),
            moderator_convergence_patience=int(defaults["moderator_convergence_patience"]),
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

    def as_flat_dict(self) -> dict[str, int | float]:
        """Return effective values as flat key/value pairs for CLI inspection."""
        return {
            "scheduler.interval_seconds": self.interval_seconds,
            "scheduler.cooldown_seconds": self.cooldown_seconds,
            "scheduler.quiet_start_hour": self.quiet_start_hour,
            "scheduler.quiet_end_hour": self.quiet_end_hour,
            "scheduler.daily_cap": self.daily_cap,
            "scheduler.jitter_percent": self.jitter_percent,
            "gate.relevance_threshold": self.relevance_threshold,
            "gate.persona_discussion_threshold": self.persona_discussion_threshold,
            "moderator.max_discussion_rounds": self.max_discussion_rounds,
            "moderator.moderator_convergence_patience": self.moderator_convergence_patience,
        }
