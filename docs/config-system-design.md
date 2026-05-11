# Unified Configuration System Design

This document outlines the new unified configuration system for NuSelf, consolidating previously scattered configuration sources (`.env`, `reflection_config.yaml`, `email.toml`, hardcoded defaults) into a single `config.yaml`.

## Goals

1. **Single source of truth**: All system configuration in one place.
2. **Environment override**: CLI and environment variables still take precedence for testing/deployment.
3. **Clear defaults**: All defaults documented in example config.
4. **Type safety**: Structured validation with defaults and clamping.
5. **Backward compatibility**: `.env` fallback for gradual migration.

## Configuration Hierarchy

Priority order (highest to lowest):
1. CLI arguments (when added)
2. Environment variables (NUSELF_* and OPENAI_*)
3. `private/config.yaml` (if present)
4. `examples/private/config.yaml` (sample, for test mode)
5. Hardcoded defaults in code

## Config.yaml Structure

```yaml
# LLM Configuration
llm:
  openai:
    base_url: https://api.openai.com/v1
    api_key: ""  # Empty = deterministic fallback
    model: gpt-4.1-mini

# Chat Agent Settings (context compression)
chat:
  context:
    recent_messages: 12         # Recent messages to keep in context
    summary_trigger_messages: 18 # When to compress context
    summary_target_chars: 2400    # Target size for compressed summary

# Daemon Background Tasks
daemon:
  memory_curator:
    interval_seconds: 300
  reflection_scheduler:
    check_interval_seconds: 60
  notification_delivery:
    interval_seconds: 30

# Proactive Reflection System
reflection:
  scheduler:
    interval_seconds: 3600        # Base interval between reflection cycles
    cooldown_seconds: 300         # Minimum time after last reflection
    quiet_start_hour: 22          # Start of quiet hours (0-23)
    quiet_end_hour: 7             # End of quiet hours (0-23)
    daily_cap: 5                  # Max reflections per day
    jitter_percent: 20            # Random jitter (0-50%)
  gate:
    relevance_threshold: 0.5      # Minimum composite score to pass
    persona_discussion_threshold: 0.7 # Score to trigger persona discussion
  moderator:
    max_discussion_rounds: 10
    moderator_convergence_patience: 5

# Email Notification Adapter (optional)
email:
  enabled: false
  smtp:
    host: localhost
    port: 587
    use_tls: true
    username: ""
    password: ""
  from_address: ""

# macOS Notification Adapter
macos_notification:
  enabled: true

# Experimental Features
experimental:
  langmem_adapter: false
  vector_index: false
```

## ConfigSystem Class

The `ConfigSystem` class replaces the scatter of `config_value()`, `config_int()`, and `ReflectionConfig` methods:

```python
@dataclass(frozen=True)
class SystemConfig:
    """Complete system configuration with nested dataclass hierarchy."""
    # Nested configs...
    llm: LlmConfig
    chat: ChatConfig
    daemon: DaemonConfig
    reflection: ReflectionConfig
    email: EmailConfig
    macos_notification: MacosNotificationConfig
    experimental: ExperimentalConfig

class ConfigSystem:
    """Unified configuration loader with env override support."""
    
    @classmethod
    def load(cls, project_root: Path | None = None) -> SystemConfig:
        """Load config from YAML with env overrides."""
        # 1. Start with defaults
        # 2. Merge YAML if present
        # 3. Apply env var overrides
        # 4. Clamp/validate values
        # 5. Return immutable config
```

## Migration Path

### Phase 1 (Current)
- New `ConfigSystem` lives alongside old config functions
- `.env` continues to work
- Tests updated to use both paths

### Phase 2 (Next Sprint)
- All production code switches to `ConfigSystem`
- Old `config_int`, `config_value`, `ReflectionConfig` deprecated
- `.env` still works as fallback

### Phase 3 (Later)
- Remove `.env` dependency for prod code
- Keep examples/.env for reference only
- Full migration to `config.yaml`

## Environment Variable Mapping

For backward compatibility, env vars still work but use new precedence:

- `OPENAI_*` → `llm.openai.*`
- `NUSELF_CONTEXT_*` → `chat.context.*`
- `NUSELF_MEMORY_CURATOR_INTERVAL_SECONDS` → `daemon.memory_curator.interval_seconds`
- `NUSELF_REFLECTION_*` → `reflection.*`
- `NUSELF_EMAIL_*` → `email.*`

## Error Handling

- Missing `config.yaml`: Use defaults (silent)
- Invalid YAML syntax: Log warning, use defaults
- Invalid field values: Clamp to safe ranges with logging
- Missing required fields like API key: Use empty string, warn at runtime when needed

## Testing

- `ConfigSystem.for_testing()` → heavily disabled/fast config
- `ConfigSystem.default()` → production defaults
- Tests can inject custom configs without file I/O
