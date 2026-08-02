"""Authority-scoped configuration helpers and unified configuration system.

Configuration lives in the selected authority's ``config.yaml``.
Uses Pydantic for type coercion, validation, and nested model loading.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from nuself.private_fs import (
    ensure_private_directory,
    harden_managed_file,
    harden_private_file,
)
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.scope import (
    NuSelfScope,
    RuntimePaths,
    resolve_runtime_paths,
    resolve_scope,
    scope_from_authority_root,
)


# ============================================================================
# Runtime Paths
# ============================================================================


def runtime_paths(
    authority: NuSelfScope | Path | None = None,
) -> RuntimePaths:
    """Resolve paths for the selected or explicit authority."""

    if authority is None:
        scope = resolve_scope()
    elif isinstance(authority, NuSelfScope):
        scope = authority
    else:
        scope = scope_from_authority_root(authority)
    return resolve_runtime_paths(scope)


def ensure_runtime_dirs(paths: RuntimePaths) -> None:
    """Create local ignored runtime directories."""

    ensure_private_directory(paths.authority_root)
    ensure_private_directory(paths.runtime_dir)
    ensure_private_directory(paths.logs_dir)
    ensure_private_directory(paths.socket_runtime_dir)


# ============================================================================
# Configuration Models
# ============================================================================


class _ConfigModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        strict=True,
        allow_inf_nan=False,
    )


class LlmEndpointConfig(_ConfigModel):

    base_url: str = ""
    api_key: str = Field(default="", repr=False)
    model: str = ""
    anthropic: bool = False
    timeout_seconds: float = Field(default=60.0, ge=1.0)

    @model_validator(mode="after")
    def _fill_anthropic_url(self) -> LlmEndpointConfig:
        if not self.base_url and self.anthropic:
            object.__setattr__(self, "base_url", "https://api.anthropic.com")
        return self


class LlmConfig(_ConfigModel):

    endpoints: tuple[LlmEndpointConfig, ...] = (
        LlmEndpointConfig(
            base_url="https://api.openai.com/v1",
            api_key="",
            model="gpt-4.1-mini",
        ),
    )


class ChatContextConfig(_ConfigModel):

    recent_messages: int = Field(default=12, ge=1)
    summary_trigger_messages: int = Field(default=18, ge=3)
    summary_target_chars: int = Field(default=2400, ge=100)


class ChatConfig(_ConfigModel):

    context: ChatContextConfig = ChatContextConfig()
    language_preference: str = "en"
    request_timeout_seconds: float = Field(default=120.0, ge=1.0)


class DaemonMemoryCuratorConfig(_ConfigModel):

    interval_seconds: int = Field(default=300, ge=1)


class DaemonReflectionSchedulerConfig(_ConfigModel):

    check_interval_seconds: int = Field(default=600, ge=1)


class DaemonNotificationDeliveryConfig(_ConfigModel):

    interval_seconds: int = Field(default=30, ge=1)


class DaemonReasonSchedulerConfig(_ConfigModel):

    interval_seconds: int = Field(default=600, ge=1)


class DaemonConfig(_ConfigModel):

    memory_curator: DaemonMemoryCuratorConfig = DaemonMemoryCuratorConfig()
    reflection_scheduler: DaemonReflectionSchedulerConfig = DaemonReflectionSchedulerConfig()
    notification_delivery: DaemonNotificationDeliveryConfig = DaemonNotificationDeliveryConfig()
    reason_scheduler: DaemonReasonSchedulerConfig = DaemonReasonSchedulerConfig()


class ReflectionSchedulerConfig(_ConfigModel):

    interval_seconds: int = Field(default=3600, ge=1)
    cooldown_seconds: int = Field(default=300, ge=0)
    quiet_start_hour: int = Field(default=22, ge=0, le=23)
    quiet_end_hour: int = Field(default=7, ge=0, le=23)
    daily_cap: int = Field(default=5, ge=1)
    jitter_percent: int = Field(default=20, ge=0, le=50)


class ReflectionGateConfig(_ConfigModel):

    relevance_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    persona_discussion_threshold: float = Field(default=0.6, ge=0.0, le=1.0)


class ReflectionModeratorConfig(_ConfigModel):

    max_discussion_rounds: int = Field(default=12, ge=1)
    moderator_convergence_patience: int = Field(default=5, ge=1)


class ReflectionDiscussionConfig(_ConfigModel):

    blocking_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    override_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    composite_threshold: float = Field(default=0.4, ge=0.0, le=1.0)
    consensus_spread_threshold: float = Field(default=0.15, ge=0.0, le=1.0)
    min_participants: int = Field(default=3, ge=1)
    max_participants: int = Field(default=5, ge=1)


class ReflectionSettings(_ConfigModel):

    scheduler: ReflectionSchedulerConfig = ReflectionSchedulerConfig()
    gate: ReflectionGateConfig = ReflectionGateConfig()
    moderator: ReflectionModeratorConfig = ReflectionModeratorConfig()
    discussion: ReflectionDiscussionConfig = ReflectionDiscussionConfig()
    auto_notify: bool = False


class EmailSmtpConfig(_ConfigModel):

    host: str = "smtp.gmail.com"
    port: int = Field(default=587, ge=1, le=65_535)
    use_tls: bool = True
    username: str = ""
    password: str = Field(default="", repr=False)


class EmailConfig(_ConfigModel):

    enabled: bool = False
    smtp: EmailSmtpConfig = EmailSmtpConfig()
    from_address: str = ""
    to_address: str = ""

    @field_validator("from_address", "to_address")
    @classmethod
    def _validate_header(cls, value: str) -> str:
        if any(
            ord(character) < 32 or ord(character) == 127
            for character in value
        ):
            raise ValueError("email address contains control characters")
        return value

    @model_validator(mode="after")
    def _validate_enabled_email(self) -> EmailConfig:
        username = self.smtp.username.strip()
        password = self.smtp.password.strip()
        if bool(username) != bool(password):
            raise ValueError(
                "email SMTP username and password must be provided together"
            )
        if self.enabled and (
            not self.smtp.host.strip()
            or not self.from_address.strip()
            or not self.to_address.strip()
        ):
            raise ValueError(
                "enabled email requires SMTP host, from_address, "
                "and to_address"
            )
        return self


class MacosNotificationConfig(_ConfigModel):

    enabled: bool = True


class ExperimentalConfig(_ConfigModel):

    vector_index: bool = False


class SystemConfig(_ConfigModel):
    """Complete NuSelf system configuration."""

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
    data: object,
    *,
    prefix: str = "",
) -> dict[str, Any]:
    """Recursively flatten config containers into scalar dotted keys."""
    result: dict[str, Any] = {}
    if isinstance(data, dict):
        mapping = cast("dict[str, Any]", data)
        for key, value in mapping.items():
            full_key = f"{prefix}.{key}" if prefix else key
            result.update(_flatten_config(value, prefix=full_key))
        return result
    if isinstance(data, (list, tuple)):
        sequence = cast("list[object] | tuple[object, ...]", data)
        for index, value in enumerate(sequence):
            full_key = f"{prefix}.{index}" if prefix else str(index)
            result.update(_flatten_config(value, prefix=full_key))
        return result
    if prefix:
        result[prefix] = data
    return result


def _redact_flat_config(flat: dict[str, Any]) -> dict[str, Any]:
    """Return a scalar effective-config projection with secrets removed."""

    return {
        key: (
            "***"
            if _is_sensitive_config_key(key) and value
            else "(not set)"
            if _is_sensitive_config_key(key)
            else value
        )
        for key, value in flat.items()
    }


def _is_sensitive_config_key(key: str) -> bool:
    field_name = key.rsplit(".", maxsplit=1)[-1].lower()
    return field_name == "api_key" or any(
        marker in field_name
        for marker in ("password", "token", "secret", "credential")
    )


class ConfigSystem:
    """Unified configuration loader."""

    @staticmethod
    def _default_config() -> SystemConfig:
        """Return safe default configuration."""
        return SystemConfig()

    @classmethod
    def load(cls, config_path: Path | None = None, project_root: Path | None = None) -> SystemConfig:
        """Load one configuration file with defaults."""
        if config_path is None and project_root is None:
            return cls.load_scope(resolve_scope())
        if config_path is None and project_root is not None:
            config_path = project_root / "config.yaml"

        if config_path and config_path.exists():
            if project_root is not None:
                ensure_private_directory(
                    runtime_paths(project_root).authority_root
                )
            harden_private_file(config_path)
        return cls._build(config_path)

    @classmethod
    def load_scope(cls, scope: NuSelfScope) -> SystemConfig:
        """Load the selected scope's layered configuration."""

        paths = resolve_runtime_paths(scope)
        layer_paths = [paths.user_config_file]
        if paths.config_file != paths.user_config_file:
            layer_paths.append(paths.config_file)

        merged_layers: dict[str, Any] = {}
        for layer_path in layer_paths:
            if not layer_path.exists():
                continue
            layer_root = (
                scope.user_root
                if layer_path == paths.user_config_file
                else scope.root
            )
            harden_managed_file(layer_root, layer_path)
            layer = cls._read_mapping(layer_path)
            cls._normalize_mapping(layer)
            merged_layers = _deep_merge(merged_layers, layer)

        defaults = cls._default_config().model_dump(mode="python")
        return SystemConfig.model_validate(
            _deep_merge(defaults, merged_layers)
        )

    @classmethod
    def _build(cls, config_path: Path | None) -> SystemConfig:
        yaml_data = (
            cls._read_mapping(config_path)
            if config_path and config_path.exists()
            else {}
        )
        cls._normalize_mapping(yaml_data)
        defaults = cls._default_config().model_dump(mode="python")
        merged = _deep_merge(defaults, yaml_data)
        return SystemConfig.model_validate(merged)

    @staticmethod
    def _read_mapping(config_path: Path) -> dict[str, Any]:
        try:
            raw: Any = yaml.safe_load(  # type: ignore[no-untyped-call]
                config_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            import sys

            print(
                f"nuself: ignoring unreadable config {config_path}: "
                f"{diagnostic_exception_message(exc)}",
                file=sys.stderr,
            )
            return {}
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            raise ValueError("NuSelf configuration root must be an object")
        return cast(dict[str, Any], raw)

    @staticmethod
    def _normalize_mapping(
        yaml_data: dict[str, Any],
    ) -> None:
        """Normalize one configuration layer before merging."""

        llm_raw: object = yaml_data.get("llm")
        if isinstance(llm_raw, list):
            endpoints = cast(list[Any], llm_raw)
            yaml_data["llm"] = {"endpoints": tuple(endpoints)}
        elif llm_raw is not None:
            raise ValueError(
                "NuSelf configuration 'llm' must be an endpoint list"
            )

    def as_flat_dict(self, config: SystemConfig) -> dict[str, Any]:
        """Return configuration as flat key/value pairs for CLI inspection."""
        raw = config.model_dump(mode="python")
        flat = _redact_flat_config(_flatten_config(raw))

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
