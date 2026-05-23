"""Unified configuration system for NuSelf.

All system configuration lives in private/config.yaml.
Uses Pydantic for type coercion, validation, and nested model loading.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


# ============================================================================
# Configuration Models
# ============================================================================


class LlmEndpointConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: str = ""
    api_key: str = ""
    model: str = ""
    anthropic: bool = False
    timeout_seconds: float = 60.0

    @model_validator(mode="after")
    def _fill_anthropic_url(self) -> LlmEndpointConfig:
        if not self.base_url and self.anthropic:
            object.__setattr__(self, "base_url", "https://api.anthropic.com/v1")
        return self


class LlmConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    endpoints: tuple[LlmEndpointConfig, ...] = (
        LlmEndpointConfig(
            base_url="https://api.openai.com/v1",
            api_key="",
            model="gpt-4.1-mini",
        ),
    )


class ChatContextConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    recent_messages: int = Field(default=12, ge=1)
    summary_trigger_messages: int = Field(default=18, ge=3)
    summary_target_chars: int = Field(default=2400, ge=100)


class ChatConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    context: ChatContextConfig = ChatContextConfig()
    language_preference: str = "en"
    request_timeout_seconds: float = Field(default=120.0, ge=1.0)


class DaemonMemoryCuratorConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    interval_seconds: int = Field(default=300, ge=1)


class DaemonReflectionSchedulerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    check_interval_seconds: int = Field(default=600, ge=1)


class DaemonNotificationDeliveryConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    interval_seconds: int = Field(default=30, ge=1)


class DaemonReasonSchedulerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    interval_seconds: int = Field(default=600, ge=1)


class DaemonConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    memory_curator: DaemonMemoryCuratorConfig = DaemonMemoryCuratorConfig()
    reflection_scheduler: DaemonReflectionSchedulerConfig = DaemonReflectionSchedulerConfig()
    notification_delivery: DaemonNotificationDeliveryConfig = DaemonNotificationDeliveryConfig()
    reason_scheduler: DaemonReasonSchedulerConfig = DaemonReasonSchedulerConfig()


class ReflectionSchedulerConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    interval_seconds: int = Field(default=3600, ge=1)
    cooldown_seconds: int = Field(default=300, ge=0)
    quiet_start_hour: int = Field(default=22, ge=0, le=23)
    quiet_end_hour: int = Field(default=7, ge=0, le=23)
    daily_cap: int = Field(default=5, ge=1)
    jitter_percent: int = Field(default=20, ge=0, le=50)


class ReflectionGateConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    relevance_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    persona_discussion_threshold: float = Field(default=0.6, ge=0.0, le=1.0)


class ReflectionModeratorConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_discussion_rounds: int = Field(default=12, ge=1)
    moderator_convergence_patience: int = Field(default=5, ge=1)


class ReflectionDiscussionConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    blocking_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    override_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    composite_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    consensus_spread_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    min_participants: int = Field(default=3, ge=1)
    max_participants: int = Field(default=5, ge=1)


class ReflectionSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    scheduler: ReflectionSchedulerConfig = ReflectionSchedulerConfig()
    gate: ReflectionGateConfig = ReflectionGateConfig()
    moderator: ReflectionModeratorConfig = ReflectionModeratorConfig()
    discussion: ReflectionDiscussionConfig = ReflectionDiscussionConfig()
    auto_notify: bool = False


class EmailSmtpConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    host: str = "smtp.gmail.com"
    port: int = Field(default=587, ge=1)
    use_tls: bool = True
    username: str = ""
    password: str = ""


class EmailConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    smtp: EmailSmtpConfig = EmailSmtpConfig()
    from_address: str = ""


class MacosNotificationConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = True


class ExperimentalConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    langmem_adapter: bool = False
    vector_index: bool = False


class SystemConfig(BaseModel):
    """Complete NuSelf system configuration."""
    model_config = ConfigDict(frozen=True, extra="ignore")

    llm: LlmConfig = LlmConfig()
    chat: ChatConfig = ChatConfig()
    daemon: DaemonConfig = DaemonConfig()
    reflection: ReflectionSettings = ReflectionSettings()
    email: EmailConfig = EmailConfig()
    macos_notification: MacosNotificationConfig = MacosNotificationConfig()
    experimental: ExperimentalConfig = ExperimentalConfig()


# ============================================================================
# Configuration Loader
# ============================================================================


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge *override* into *base* (mutating base), return base."""
    for key, val in override.items():
        if isinstance(val, dict):
            existing: Any = base.get(key)
            if isinstance(existing, dict):
                _deep_merge(cast("dict[str, Any]", existing), cast("dict[str, Any]", val))
            else:
                base[key] = val
        else:
            base[key] = val
    return base


def _flatten_config(
    data: dict[str, Any],
    *,
    prefix: str = "",
) -> dict[str, Any]:
    """Recursively flatten a nested config dict into dotted keys."""
    result: dict[str, Any] = {}
    for key, val in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(val, dict):
            d = cast("dict[str, Any]", val)
            if d and not any(isinstance(v, dict) for v in d.values()):
                for sub_key, sub_val in d.items():
                    result[f"{full_key}.{sub_key}"] = sub_val
            else:
                result.update(_flatten_config(d, prefix=full_key))
        else:
            result[full_key] = val
    return result


class ConfigSystem:
    """Unified configuration loader."""

    @staticmethod
    def _default_config() -> SystemConfig:
        """Return safe default configuration."""
        return SystemConfig()

    @staticmethod
    def _test_config() -> SystemConfig:
        """Return fast configuration suitable for testing."""
        return SystemConfig(
            daemon=DaemonConfig(
                memory_curator=DaemonMemoryCuratorConfig(interval_seconds=5),
                reflection_scheduler=DaemonReflectionSchedulerConfig(check_interval_seconds=1),
                notification_delivery=DaemonNotificationDeliveryConfig(interval_seconds=1),
                reason_scheduler=DaemonReasonSchedulerConfig(interval_seconds=1),
            ),
            reflection=ReflectionSettings(
                scheduler=ReflectionSchedulerConfig(
                    interval_seconds=10,
                    cooldown_seconds=0,
                    quiet_start_hour=23,
                    quiet_end_hour=23,
                    daily_cap=100,
                    jitter_percent=0,
                ),
                gate=ReflectionGateConfig(
                    relevance_threshold=0.0,
                    persona_discussion_threshold=1.0,
                ),
                moderator=ReflectionModeratorConfig(
                    max_discussion_rounds=2,
                    moderator_convergence_patience=1,
                ),
                discussion=ReflectionDiscussionConfig(),
                auto_notify=False,
            ),
        )

    @classmethod
    def load(cls, config_path: Path | None = None, project_root: Path | None = None) -> SystemConfig:
        """Load configuration from YAML with defaults."""
        if config_path is None and project_root is None:
            from nuself.config import find_project_root
            project_root = find_project_root()
        if config_path is None and project_root is not None:
            config_path = project_root / "private" / "config.yaml"

        yaml_data: dict[str, Any] = {}
        if config_path and config_path.exists():
            try:
                raw: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))  # type: ignore[no-untyped-call]
                yaml_data = cast(dict[str, Any], raw if isinstance(raw, dict) else {})
            except Exception:
                pass

        # Normalize llm: [...] (YAML list) to llm: {endpoints: [...]}
        llm_raw: object = yaml_data.get("llm")
        if isinstance(llm_raw, list):
            yaml_data["llm"] = {"endpoints": llm_raw}
        elif isinstance(llm_raw, dict) and "endpoints" not in llm_raw:
            # Nested dict that doesn't match LlmConfig schema — use defaults
            del yaml_data["llm"]

        # Deep-merge YAML over defaults, then validate
        defaults = cls._default_config().model_dump(mode="python")
        merged = _deep_merge(defaults, yaml_data)
        return SystemConfig.model_validate(merged)

    def as_flat_dict(self, config: SystemConfig) -> dict[str, Any]:
        """Return configuration as flat key/value pairs for CLI inspection."""
        raw = config.model_dump(mode="python")
        flat = _flatten_config(raw)

        # Special handling for LLM endpoints
        flat["llm.count"] = len(config.llm.endpoints)
        if config.llm.endpoints:
            flat["llm.0.provider"] = "anthropic" if config.llm.endpoints[0].anthropic else "openai"
            flat["llm.0.base_url"] = config.llm.endpoints[0].base_url
            flat["llm.0.api_key"] = "***" if config.llm.endpoints[0].api_key else "(not set)"
            flat["llm.0.model"] = config.llm.endpoints[0].model
        else:
            flat["llm.0.provider"] = "(not set)"
            flat["llm.0.base_url"] = "(not set)"
            flat["llm.0.api_key"] = "(not set)"
            flat["llm.0.model"] = "(not set)"

        return flat
