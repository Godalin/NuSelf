"""Unified configuration system for NuSelf.

All system configuration lives in private/config.yaml with environment
variable overrides. This replaces the scattered .env, reflection_config.yaml,
and hardcoded defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, cast

import yaml


# ============================================================================
# Configuration Data Classes
# ============================================================================


@dataclass(frozen=True)
class LlmOpenAiConfig:
    """OpenAI-compatible LLM configuration."""
    base_url: str
    api_key: str
    model: str


@dataclass(frozen=True)
class LlmConfig:
    """LLM provider configuration."""
    openai: LlmOpenAiConfig


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
class ReflectionSettings:
    """Proactive reflection system configuration."""
    scheduler: ReflectionSchedulerConfig
    gate: ReflectionGateConfig
    moderator: ReflectionModeratorConfig


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
    """Unified configuration loader with environment overrides."""

    @staticmethod
    def _default_config() -> SystemConfig:
        """Return safe default configuration."""
        return SystemConfig(
            llm=LlmConfig(
                openai=LlmOpenAiConfig(
                    base_url="https://api.openai.com/v1",
                    api_key="",
                    model="gpt-4.1-mini",
                )
            ),
            chat=ChatConfig(
                context=ChatContextConfig(
                    recent_messages=12,
                    summary_trigger_messages=18,
                    summary_target_chars=2400,
                )
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
                    relevance_threshold=0.5,
                    persona_discussion_threshold=0.7,
                ),
                moderator=ReflectionModeratorConfig(
                    max_discussion_rounds=10,
                    moderator_convergence_patience=5,
                ),
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
            ),
            email=defaults.email,
            macos_notification=defaults.macos_notification,
            experimental=defaults.experimental,
        )

    @classmethod
    def load(cls, config_path: Path | None = None, project_root: Path | None = None) -> SystemConfig:
        """Load configuration from YAML with env overrides and defaults."""
        if config_path is None and project_root is None:
            from nuself.config import find_project_root
            project_root = find_project_root()
        if config_path is None and project_root is not None:
            config_path = project_root / "private" / "config.yaml"

        # Load .env file if present (so environment variables are available)
        cls._load_env_file(project_root)

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

        # Merge and apply environment overrides
        return cls._merge_with_env_overrides(defaults, yaml_data)
    
    @staticmethod
    def _load_env_file(project_root: Path | None = None) -> None:
        """Load .env file into os.environ if it exists."""
        if project_root is None:
            from nuself.config import find_project_root
            project_root = find_project_root()
        
        env_file = project_root / ".env"
        if not env_file.exists():
            return
        
        try:
            env_content = env_file.read_text(encoding="utf-8")
            for line in env_content.split("\n"):
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith("#"):
                    continue
                # Parse KEY=VALUE
                if "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    # Only set if not already in environment (YAML/CLI values take precedence)
                    if key not in os.environ:
                        os.environ[key] = value
        except Exception:
            # Fail silently, continue without .env
            pass

    @staticmethod
    def _merge_with_env_overrides(defaults: SystemConfig, yaml_data: dict[str, Any]) -> SystemConfig:
        """Merge YAML config with environment variable overrides."""

        def get_str(d: dict[str, Any], path: str, default: str) -> str:
            """Get string value from nested dict, env override, or default."""
            env_key = f"NUSELF_{path.upper().replace('.', '_')}"
            if env_key in os.environ:
                return os.environ[env_key]
            keys = path.split(".")
            val: Any = d
            for key in keys:
                if isinstance(val, dict):
                    val = val.get(key)  # type: ignore[union-attr]
                else:
                    val = None
                    break
            if isinstance(val, str):
                return val
            return default

        def get_int(d: dict[str, Any], path: str, default: int) -> int:
            """Get int value from nested dict, env override, or default."""
            env_key = f"NUSELF_{path.upper().replace('.', '_')}"
            if env_key in os.environ:
                try:
                    return int(os.environ[env_key])
                except ValueError:
                    pass
            keys = path.split(".")
            val: Any = d
            for key in keys:
                if isinstance(val, dict):
                    val = val.get(key)  # type: ignore[union-attr]
                else:
                    val = None
                    break
            if isinstance(val, int):
                return val
            if isinstance(val, str):
                try:
                    return int(val)
                except ValueError:
                    pass
            return default

        def get_float(d: dict[str, Any], path: str, default: float) -> float:
            """Get float value from nested dict, env override, or default."""
            env_key = f"NUSELF_{path.upper().replace('.', '_')}"
            if env_key in os.environ:
                try:
                    return float(os.environ[env_key])
                except ValueError:
                    pass
            keys = path.split(".")
            val: Any = d
            for key in keys:
                if isinstance(val, dict):
                    val = val.get(key)  # type: ignore[union-attr]
                else:
                    val = None
                    break
            if isinstance(val, (int, float)):
                return float(val)
            if isinstance(val, str):
                try:
                    return float(val)
                except ValueError:
                    pass
            return default

        def get_bool(d: dict[str, Any], path: str, default: bool) -> bool:
            """Get bool value from nested dict, env override, or default."""
            env_key = f"NUSELF_{path.upper().replace('.', '_')}"
            if env_key in os.environ:
                return os.environ[env_key].lower() in {"true", "yes", "1", "on"}
            keys = path.split(".")
            val: Any = d
            for key in keys:
                if isinstance(val, dict):
                    val = val.get(key)  # type: ignore[union-attr]
                else:
                    val = None
                    break
            if isinstance(val, bool):
                return val
            return default

        # LLM Config
        openai_base_url = get_str(yaml_data, "llm.openai.base_url", defaults.llm.openai.base_url)
        openai_api_key = get_str(yaml_data, "llm.openai.api_key", defaults.llm.openai.api_key)
        # Also check OPENAI_* env vars for backward compat
        if "OPENAI_API_KEY" in os.environ:
            openai_api_key = os.environ["OPENAI_API_KEY"]
        if "OPENAI_BASE_URL" in os.environ:
            openai_base_url = os.environ["OPENAI_BASE_URL"]
        openai_model = get_str(yaml_data, "llm.openai.model", defaults.llm.openai.model)
        if "OPENAI_MODEL" in os.environ:
            openai_model = os.environ["OPENAI_MODEL"]

        # Chat Config
        recent_messages = max(1, get_int(yaml_data, "chat.context.recent_messages", defaults.chat.context.recent_messages))
        summary_trigger = max(recent_messages + 2, get_int(yaml_data, "chat.context.summary_trigger_messages", defaults.chat.context.summary_trigger_messages))
        summary_target = max(100, get_int(yaml_data, "chat.context.summary_target_chars", defaults.chat.context.summary_target_chars))

        # Daemon Config
        curator_interval = max(1, get_int(yaml_data, "daemon.memory_curator.interval_seconds", defaults.daemon.memory_curator.interval_seconds))
        reflection_check = max(1, get_int(yaml_data, "daemon.reflection_scheduler.check_interval_seconds", defaults.daemon.reflection_scheduler.check_interval_seconds))
        notification_interval = max(1, get_int(yaml_data, "daemon.notification_delivery.interval_seconds", defaults.daemon.notification_delivery.interval_seconds))

        # Reflection Config
        refl_interval = max(60, get_int(yaml_data, "reflection.scheduler.interval_seconds", defaults.reflection.scheduler.interval_seconds))
        refl_cooldown = max(0, get_int(yaml_data, "reflection.scheduler.cooldown_seconds", defaults.reflection.scheduler.cooldown_seconds))
        refl_quiet_start = max(0, min(get_int(yaml_data, "reflection.scheduler.quiet_start_hour", defaults.reflection.scheduler.quiet_start_hour), 23))
        refl_quiet_end = max(0, min(get_int(yaml_data, "reflection.scheduler.quiet_end_hour", defaults.reflection.scheduler.quiet_end_hour), 23))
        refl_daily_cap = max(1, get_int(yaml_data, "reflection.scheduler.daily_cap", defaults.reflection.scheduler.daily_cap))
        refl_jitter = max(0, min(get_int(yaml_data, "reflection.scheduler.jitter_percent", defaults.reflection.scheduler.jitter_percent), 50))
        refl_relevance = max(0.0, min(get_float(yaml_data, "reflection.gate.relevance_threshold", defaults.reflection.gate.relevance_threshold), 1.0))
        refl_discussion = max(0.0, min(get_float(yaml_data, "reflection.gate.persona_discussion_threshold", defaults.reflection.gate.persona_discussion_threshold), 1.0))
        refl_max_rounds = max(1, get_int(yaml_data, "reflection.moderator.max_discussion_rounds", defaults.reflection.moderator.max_discussion_rounds))
        refl_patience = max(1, get_int(yaml_data, "reflection.moderator.moderator_convergence_patience", defaults.reflection.moderator.moderator_convergence_patience))

        # Email Config
        email_enabled = get_bool(yaml_data, "email.enabled", defaults.email.enabled)
        email_host = get_str(yaml_data, "email.smtp.host", defaults.email.smtp.host)
        email_port = max(1, get_int(yaml_data, "email.smtp.port", defaults.email.smtp.port))
        email_tls = get_bool(yaml_data, "email.smtp.use_tls", defaults.email.smtp.use_tls)
        email_user = get_str(yaml_data, "email.smtp.username", defaults.email.smtp.username)
        email_pass = get_str(yaml_data, "email.smtp.password", defaults.email.smtp.password)
        email_from = get_str(yaml_data, "email.from_address", defaults.email.from_address)

        # macOS Notification Config
        macos_enabled = get_bool(yaml_data, "macos_notification.enabled", defaults.macos_notification.enabled)

        # Experimental Config
        exp_langmem = get_bool(yaml_data, "experimental.langmem_adapter", defaults.experimental.langmem_adapter)
        exp_vector = get_bool(yaml_data, "experimental.vector_index", defaults.experimental.vector_index)

        return SystemConfig(
            llm=LlmConfig(
                openai=LlmOpenAiConfig(
                    base_url=openai_base_url,
                    api_key=openai_api_key,
                    model=openai_model,
                )
            ),
            chat=ChatConfig(
                context=ChatContextConfig(
                    recent_messages=recent_messages,
                    summary_trigger_messages=summary_trigger,
                    summary_target_chars=summary_target,
                )
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
            "llm.openai.base_url": config.llm.openai.base_url,
            "llm.openai.api_key": "***" if config.llm.openai.api_key else "(not set)",
            "llm.openai.model": config.llm.openai.model,
            "chat.context.recent_messages": config.chat.context.recent_messages,
            "chat.context.summary_trigger_messages": config.chat.context.summary_trigger_messages,
            "chat.context.summary_target_chars": config.chat.context.summary_target_chars,
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
            "email.enabled": config.email.enabled,
            "macos_notification.enabled": config.macos_notification.enabled,
            "experimental.langmem_adapter": config.experimental.langmem_adapter,
            "experimental.vector_index": config.experimental.vector_index,
        }
