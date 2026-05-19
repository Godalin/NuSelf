"""Unified configuration system for NuSelf.

All system configuration lives in private/config.yaml.
This replaces previously scattered reflection_config.yaml
and hardcoded defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import yaml


# ============================================================================
# Configuration Data Classes
# ============================================================================


def _llm_endpoints_from_yaml(
    yaml_data: dict[str, Any], default: tuple["LlmEndpointConfig", ...]
) -> tuple["LlmEndpointConfig", ...]:
    llm_raw = cast(object, yaml_data.get("llm"))
    if isinstance(llm_raw, list):
        return _llm_endpoint_list_from_raw(cast(list[object], llm_raw), default)
    return default


def _llm_endpoint_list_from_raw(
    raw_list: list[object], default: tuple["LlmEndpointConfig", ...]
) -> tuple["LlmEndpointConfig", ...]:
    endpoints: list[LlmEndpointConfig] = []
    for item in raw_list:
        if not isinstance(item, dict):
            continue
        endpoint = _llm_endpoint_config_from_raw(cast(dict[object, object], item))
        if endpoint is not None:
            endpoints.append(endpoint)
    return tuple(endpoints) if endpoints else default


def _llm_endpoint_config_from_raw(raw: dict[object, object]) -> "LlmEndpointConfig | None":
    anthropic = raw.get("anthropic") is True
    base_url = raw.get("base_url")
    api_key = raw.get("api_key")
    model = raw.get("model")
    if anthropic and base_url is None:
        base_url = "https://api.anthropic.com/v1"
    if not isinstance(base_url, str) or not isinstance(api_key, str) or not isinstance(model, str):
        return None
    timeout_seconds = _positive_float(raw.get("timeout_seconds"), 60.0)
    return LlmEndpointConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        anthropic=anthropic,
        timeout_seconds=timeout_seconds,
    )


def _positive_float(raw: object, default: float) -> float:
    if isinstance(raw, (int, float)) and raw > 0:
        return float(raw)
    if isinstance(raw, str):
        try:
            value = float(raw)
        except ValueError:
            return default
        return value if value > 0 else default
    return default


def _nested_config_value(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        value = cast(dict[str, Any], value).get(key)
    return value


def _config_str(data: dict[str, Any], path: str, default: str) -> str:
    value = _nested_config_value(data, path)
    return value if isinstance(value, str) else default


def _config_int(data: dict[str, Any], path: str, default: int) -> int:
    value = _nested_config_value(data, path)
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _config_float(data: dict[str, Any], path: str, default: float) -> float:
    value = _nested_config_value(data, path)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _config_bool(data: dict[str, Any], path: str, default: bool) -> bool:
    value = _nested_config_value(data, path)
    return value if isinstance(value, bool) else default


@dataclass(frozen=True)
class LlmEndpointConfig:
    """LLM endpoint configuration."""
    base_url: str
    api_key: str
    model: str
    anthropic: bool = False
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class LlmConfig:
    """LLM provider configuration."""
    endpoints: tuple[LlmEndpointConfig, ...]


@dataclass(frozen=True)
class ChatContextConfig:
    """Chat context compression settings."""
    recent_messages: int
    summary_trigger_messages: int
    summary_target_chars: int


@dataclass(frozen=True)
class ChatConfig:
    """Chat agent configuration."""
    context: ChatContextConfig
    language_preference: str = "en"
    request_timeout_seconds: float = 120.0


@dataclass(frozen=True)
class DaemonMemoryCuratorConfig:
    """Memory curator background task."""
    interval_seconds: int


@dataclass(frozen=True)
class DaemonReflectionSchedulerConfig:
    """Reflection scheduler background task."""
    check_interval_seconds: int


@dataclass(frozen=True)
class DaemonNotificationDeliveryConfig:
    """Notification delivery background task."""
    interval_seconds: int


@dataclass(frozen=True)
class DaemonConfig:
    """Daemon background task configuration."""
    memory_curator: DaemonMemoryCuratorConfig
    reflection_scheduler: DaemonReflectionSchedulerConfig
    notification_delivery: DaemonNotificationDeliveryConfig


@dataclass(frozen=True)
class ReflectionSchedulerConfig:
    """Reflection scheduling parameters."""
    interval_seconds: int
    cooldown_seconds: int
    quiet_start_hour: int
    quiet_end_hour: int
    daily_cap: int
    jitter_percent: int


@dataclass(frozen=True)
class ReflectionGateConfig:
    """Relevance gate for proactive candidates."""
    relevance_threshold: float
    persona_discussion_threshold: float


@dataclass(frozen=True)
class ReflectionModeratorConfig:
    """Persona discussion moderator settings."""
    max_discussion_rounds: int
    moderator_convergence_patience: int


@dataclass(frozen=True)
class ReflectionDiscussionConfig:
    """Competitive persona discussion parameters."""
    blocking_threshold: float = 0.35
    override_threshold: float = 0.7
    composite_threshold: float = 0.4
    consensus_spread_threshold: float = 0.15
    min_participants: int = 3
    max_participants: int = 5


@dataclass(frozen=True)
class ReflectionSettings:
    """Proactive reflection system configuration."""
    scheduler: ReflectionSchedulerConfig
    gate: ReflectionGateConfig
    moderator: ReflectionModeratorConfig
    discussion: ReflectionDiscussionConfig
    auto_notify: bool = False


@dataclass(frozen=True)
class EmailSmtpConfig:
    """SMTP server configuration."""
    host: str
    port: int
    use_tls: bool
    username: str
    password: str


@dataclass(frozen=True)
class EmailConfig:
    """Email adapter configuration."""
    enabled: bool
    smtp: EmailSmtpConfig
    from_address: str


@dataclass(frozen=True)
class MacosNotificationConfig:
    """macOS notification adapter configuration."""
    enabled: bool


@dataclass(frozen=True)
class ExperimentalConfig:
    """Feature flags for experimental features."""
    langmem_adapter: bool
    vector_index: bool


@dataclass(frozen=True)
class SystemConfig:
    """Complete NuSelf system configuration."""
    llm: LlmConfig
    chat: ChatConfig
    daemon: DaemonConfig
    reflection: ReflectionSettings
    email: EmailConfig
    macos_notification: MacosNotificationConfig
    experimental: ExperimentalConfig


# ============================================================================
# Configuration Loader
# ============================================================================


class ConfigSystem:
    """Unified configuration loader."""

    @staticmethod
    def _default_config() -> SystemConfig:
        """Return safe default configuration."""
        return SystemConfig(
            llm=LlmConfig(
                endpoints=(
                    LlmEndpointConfig(
                        base_url="https://api.openai.com/v1",
                        api_key="",
                        model="gpt-4.1-mini",
                    ),
                ),
            ),
            chat=ChatConfig(
                context=ChatContextConfig(
                    recent_messages=12,
                    summary_trigger_messages=18,
                    summary_target_chars=2400,
                ),
                language_preference="en",
                request_timeout_seconds=120.0,
            ),
            daemon=DaemonConfig(
                memory_curator=DaemonMemoryCuratorConfig(interval_seconds=300),
                reflection_scheduler=DaemonReflectionSchedulerConfig(check_interval_seconds=600),
                notification_delivery=DaemonNotificationDeliveryConfig(interval_seconds=30),
            ),
            reflection=ReflectionSettings(
                scheduler=ReflectionSchedulerConfig(
                    interval_seconds=3600,
                    cooldown_seconds=300,
                    quiet_start_hour=22,
                    quiet_end_hour=7,
                    daily_cap=5,
                    jitter_percent=20,
                ),
                gate=ReflectionGateConfig(
                    relevance_threshold=0.4,
                    persona_discussion_threshold=0.6,
                ),
                moderator=ReflectionModeratorConfig(
                    max_discussion_rounds=12,
                    moderator_convergence_patience=5,
                ),
                discussion=ReflectionDiscussionConfig(
                    blocking_threshold=0.35,
                    override_threshold=0.7,
                    composite_threshold=0.4,
                    consensus_spread_threshold=0.15,
                    min_participants=3,
                    max_participants=5,
                ),
                auto_notify=False,
            ),
            email=EmailConfig(
                enabled=False,
                smtp=EmailSmtpConfig(
                    host="smtp.gmail.com",
                    port=587,
                    use_tls=True,
                    username="",
                    password="",
                ),
                from_address="",
            ),
            macos_notification=MacosNotificationConfig(enabled=True),
            experimental=ExperimentalConfig(
                langmem_adapter=False,
                vector_index=False,
            ),
        )

    @staticmethod
    def _test_config() -> SystemConfig:
        """Return fast configuration suitable for testing."""
        defaults = ConfigSystem._default_config()
        return SystemConfig(
            llm=defaults.llm,
            chat=defaults.chat,
            daemon=DaemonConfig(
                memory_curator=DaemonMemoryCuratorConfig(interval_seconds=5),
                reflection_scheduler=DaemonReflectionSchedulerConfig(check_interval_seconds=1),
                notification_delivery=DaemonNotificationDeliveryConfig(interval_seconds=1),
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
            email=defaults.email,
            macos_notification=defaults.macos_notification,
            experimental=defaults.experimental,
        )

    @classmethod
    def load(cls, config_path: Path | None = None, project_root: Path | None = None) -> SystemConfig:
        """Load configuration from YAML with defaults."""
        if config_path is None and project_root is None:
            from nuself.config import find_project_root
            project_root = find_project_root()
        if config_path is None and project_root is not None:
            config_path = project_root / "private" / "config.yaml"

        # Start with defaults
        defaults = cls._default_config()

        # Load YAML if present
        yaml_data: dict[str, Any] = {}
        if config_path and config_path.exists():
            try:
                raw: Any = yaml.safe_load(config_path.read_text(encoding="utf-8"))  # type: ignore[no-untyped-call]
                yaml_data = cast(dict[str, Any], raw if isinstance(raw, dict) else {})
            except Exception:
                # Fail silently, use defaults
                pass

        # Merge YAML over defaults
        return cls._merge_yaml_with_defaults(defaults, yaml_data)

    @staticmethod
    def _merge_yaml_with_defaults(defaults: SystemConfig, yaml_data: dict[str, Any]) -> SystemConfig:
        """Merge YAML config over hardcoded defaults."""

        # LLM Config
        llm_endpoints = _llm_endpoints_from_yaml(yaml_data, defaults.llm.endpoints)

        # Chat Config
        recent_messages = max(1, _config_int(yaml_data, "chat.context.recent_messages", defaults.chat.context.recent_messages))
        summary_trigger = max(recent_messages + 2, _config_int(yaml_data, "chat.context.summary_trigger_messages", defaults.chat.context.summary_trigger_messages))
        summary_target = max(100, _config_int(yaml_data, "chat.context.summary_target_chars", defaults.chat.context.summary_target_chars))
        chat_language = _config_str(yaml_data, "chat.language_preference", defaults.chat.language_preference)
        chat_request_timeout = max(
            1.0,
            _config_float(yaml_data, "chat.request_timeout_seconds", defaults.chat.request_timeout_seconds),
        )

        # Daemon Config
        curator_interval = max(1, _config_int(yaml_data, "daemon.memory_curator.interval_seconds", defaults.daemon.memory_curator.interval_seconds))
        reflection_check = max(1, _config_int(yaml_data, "daemon.reflection_scheduler.check_interval_seconds", defaults.daemon.reflection_scheduler.check_interval_seconds))
        notification_interval = max(1, _config_int(yaml_data, "daemon.notification_delivery.interval_seconds", defaults.daemon.notification_delivery.interval_seconds))

        # Reflection Config
        refl_interval = max(60, _config_int(yaml_data, "reflection.scheduler.interval_seconds", defaults.reflection.scheduler.interval_seconds))
        refl_cooldown = max(0, _config_int(yaml_data, "reflection.scheduler.cooldown_seconds", defaults.reflection.scheduler.cooldown_seconds))
        refl_quiet_start = max(0, min(_config_int(yaml_data, "reflection.scheduler.quiet_start_hour", defaults.reflection.scheduler.quiet_start_hour), 23))
        refl_quiet_end = max(0, min(_config_int(yaml_data, "reflection.scheduler.quiet_end_hour", defaults.reflection.scheduler.quiet_end_hour), 23))
        refl_daily_cap = max(1, _config_int(yaml_data, "reflection.scheduler.daily_cap", defaults.reflection.scheduler.daily_cap))
        refl_jitter = max(0, min(_config_int(yaml_data, "reflection.scheduler.jitter_percent", defaults.reflection.scheduler.jitter_percent), 50))
        refl_relevance = max(0.0, min(_config_float(yaml_data, "reflection.gate.relevance_threshold", defaults.reflection.gate.relevance_threshold), 1.0))
        refl_discussion = max(0.0, min(_config_float(yaml_data, "reflection.gate.persona_discussion_threshold", defaults.reflection.gate.persona_discussion_threshold), 1.0))
        refl_max_rounds = max(1, _config_int(yaml_data, "reflection.moderator.max_discussion_rounds", defaults.reflection.moderator.max_discussion_rounds))
        refl_patience = max(1, _config_int(yaml_data, "reflection.moderator.moderator_convergence_patience", defaults.reflection.moderator.moderator_convergence_patience))
        refl_blocking = max(0.0, min(_config_float(yaml_data, "reflection.discussion.blocking_threshold", defaults.reflection.discussion.blocking_threshold), 1.0))
        refl_override = max(0.0, min(_config_float(yaml_data, "reflection.discussion.override_threshold", defaults.reflection.discussion.override_threshold), 1.0))
        refl_composite = max(0.0, min(_config_float(yaml_data, "reflection.discussion.composite_threshold", defaults.reflection.discussion.composite_threshold), 1.0))
        refl_spread = max(0.0, min(_config_float(yaml_data, "reflection.discussion.consensus_spread_threshold", defaults.reflection.discussion.consensus_spread_threshold), 1.0))
        refl_min_participants = max(1, _config_int(yaml_data, "reflection.discussion.min_participants", defaults.reflection.discussion.min_participants))
        refl_max_participants = max(1, _config_int(yaml_data, "reflection.discussion.max_participants", defaults.reflection.discussion.max_participants))
        refl_auto_notify = _config_bool(yaml_data, "reflection.auto_notify", defaults.reflection.auto_notify)

        # Email Config
        email_enabled = _config_bool(yaml_data, "email.enabled", defaults.email.enabled)
        email_host = _config_str(yaml_data, "email.smtp.host", defaults.email.smtp.host)
        email_port = max(1, _config_int(yaml_data, "email.smtp.port", defaults.email.smtp.port))
        email_tls = _config_bool(yaml_data, "email.smtp.use_tls", defaults.email.smtp.use_tls)
        email_user = _config_str(yaml_data, "email.smtp.username", defaults.email.smtp.username)
        email_pass = _config_str(yaml_data, "email.smtp.password", defaults.email.smtp.password)
        email_from = _config_str(yaml_data, "email.from_address", defaults.email.from_address)

        # macOS Notification Config
        macos_enabled = _config_bool(yaml_data, "macos_notification.enabled", defaults.macos_notification.enabled)

        # Experimental Config
        exp_langmem = _config_bool(yaml_data, "experimental.langmem_adapter", defaults.experimental.langmem_adapter)
        exp_vector = _config_bool(yaml_data, "experimental.vector_index", defaults.experimental.vector_index)

        return SystemConfig(
            llm=LlmConfig(
                endpoints=llm_endpoints,
            ),
            chat=ChatConfig(
                context=ChatContextConfig(
                    recent_messages=recent_messages,
                    summary_trigger_messages=summary_trigger,
                    summary_target_chars=summary_target,
                ),
                language_preference=chat_language,
                request_timeout_seconds=chat_request_timeout,
            ),
            daemon=DaemonConfig(
                memory_curator=DaemonMemoryCuratorConfig(interval_seconds=curator_interval),
                reflection_scheduler=DaemonReflectionSchedulerConfig(check_interval_seconds=reflection_check),
                notification_delivery=DaemonNotificationDeliveryConfig(interval_seconds=notification_interval),
            ),
            reflection=ReflectionSettings(
                scheduler=ReflectionSchedulerConfig(
                    interval_seconds=refl_interval,
                    cooldown_seconds=refl_cooldown,
                    quiet_start_hour=refl_quiet_start,
                    quiet_end_hour=refl_quiet_end,
                    daily_cap=refl_daily_cap,
                    jitter_percent=refl_jitter,
                ),
                gate=ReflectionGateConfig(
                    relevance_threshold=refl_relevance,
                    persona_discussion_threshold=refl_discussion,
                ),
                moderator=ReflectionModeratorConfig(
                    max_discussion_rounds=refl_max_rounds,
                    moderator_convergence_patience=refl_patience,
                ),
                discussion=ReflectionDiscussionConfig(
                    blocking_threshold=refl_blocking,
                    override_threshold=refl_override,
                    composite_threshold=refl_composite,
                    consensus_spread_threshold=refl_spread,
                    min_participants=refl_min_participants,
                    max_participants=refl_max_participants,
                ),
                auto_notify=refl_auto_notify,
            ),
            email=EmailConfig(
                enabled=email_enabled,
                smtp=EmailSmtpConfig(
                    host=email_host,
                    port=email_port,
                    use_tls=email_tls,
                    username=email_user,
                    password=email_pass,
                ),
                from_address=email_from,
            ),
            macos_notification=MacosNotificationConfig(enabled=macos_enabled),
            experimental=ExperimentalConfig(
                langmem_adapter=exp_langmem,
                vector_index=exp_vector,
            ),
        )

    def as_flat_dict(self, config: SystemConfig) -> dict[str, Any]:
        """Return configuration as flat key/value pairs for CLI inspection."""
        return {
            "llm.count": len(config.llm.endpoints),
            "llm.0.provider": "anthropic" if config.llm.endpoints and config.llm.endpoints[0].anthropic else "openai",
            "llm.0.base_url": config.llm.endpoints[0].base_url if config.llm.endpoints else "(not set)",
            "llm.0.api_key": "***" if config.llm.endpoints and config.llm.endpoints[0].api_key else "(not set)",
            "llm.0.model": config.llm.endpoints[0].model if config.llm.endpoints else "(not set)",
            "chat.context.recent_messages": config.chat.context.recent_messages,
            "chat.context.summary_trigger_messages": config.chat.context.summary_trigger_messages,
            "chat.context.summary_target_chars": config.chat.context.summary_target_chars,
            "chat.language_preference": config.chat.language_preference,
            "chat.request_timeout_seconds": config.chat.request_timeout_seconds,
            "daemon.memory_curator.interval_seconds": config.daemon.memory_curator.interval_seconds,
            "daemon.reflection_scheduler.check_interval_seconds": config.daemon.reflection_scheduler.check_interval_seconds,
            "daemon.notification_delivery.interval_seconds": config.daemon.notification_delivery.interval_seconds,
            "reflection.scheduler.interval_seconds": config.reflection.scheduler.interval_seconds,
            "reflection.scheduler.cooldown_seconds": config.reflection.scheduler.cooldown_seconds,
            "reflection.scheduler.quiet_start_hour": config.reflection.scheduler.quiet_start_hour,
            "reflection.scheduler.quiet_end_hour": config.reflection.scheduler.quiet_end_hour,
            "reflection.scheduler.daily_cap": config.reflection.scheduler.daily_cap,
            "reflection.scheduler.jitter_percent": config.reflection.scheduler.jitter_percent,
            "reflection.gate.relevance_threshold": config.reflection.gate.relevance_threshold,
            "reflection.gate.persona_discussion_threshold": config.reflection.gate.persona_discussion_threshold,
            "reflection.moderator.max_discussion_rounds": config.reflection.moderator.max_discussion_rounds,
            "reflection.moderator.moderator_convergence_patience": config.reflection.moderator.moderator_convergence_patience,
            "reflection.discussion.blocking_threshold": config.reflection.discussion.blocking_threshold,
            "reflection.discussion.override_threshold": config.reflection.discussion.override_threshold,
            "reflection.discussion.composite_threshold": config.reflection.discussion.composite_threshold,
            "reflection.discussion.consensus_spread_threshold": config.reflection.discussion.consensus_spread_threshold,
            "reflection.discussion.min_participants": config.reflection.discussion.min_participants,
            "reflection.discussion.max_participants": config.reflection.discussion.max_participants,
            "email.enabled": config.email.enabled,
            "macos_notification.enabled": config.macos_notification.enabled,
            "experimental.langmem_adapter": config.experimental.langmem_adapter,
            "experimental.vector_index": config.experimental.vector_index,
        }
