# Unified Configuration System Design

This document outlines the unified configuration system for NuSelf, consolidating previously scattered configuration sources (`.env`, `reflection_config.yaml`, `email.toml`, hardcoded defaults) into a single `config.yaml`.

## Goals

1. **Single source of truth**: All system configuration in one place.
2. **Clear defaults**: All defaults documented in example config.
3. **Type safety**: Structured validation with defaults and clamping.
4. **No legacy fallback**: old reflection config and `.env` parsing are removed from runtime paths.

## Configuration Hierarchy

Priority order (highest to lowest):
1. `private/config.yaml` (if present)
2. `examples/private/config.yaml` (sample, for test mode)
3. Hardcoded defaults in code

## Config.yaml Structure

```yaml
# LLM Configuration
llm:
  - base_url: https://api.openai.com/v1
    api_key: ""  # Empty = deterministic fallback
    model: gpt-4.1-mini
  # Optional Anthropic endpoint:
  # - anthropic: true
  #   api_key: ""
  #   model: claude-sonnet-4-5

# Chat Agent Settings (context compression and language preference)
chat:
  language_preference: en
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

The `ConfigSystem` class replaces the scatter of legacy config helpers and reflection-only config classes:

```python
@dataclass(frozen=True)
class SystemConfig:
    """Complete system configuration with nested dataclass hierarchy."""
    # Nested configs...
    llm: LlmConfig
    chat: ChatConfig
    daemon: DaemonConfig
    reflection: ReflectionSettings
    email: EmailConfig
    macos_notification: MacosNotificationConfig
    experimental: ExperimentalConfig

class ConfigSystem:
    """Unified configuration loader."""
    
    @classmethod
    def load(cls, project_root: Path | None = None) -> SystemConfig:
        """Load config from YAML with defaults."""
        # 1. Start with defaults
        # 2. Merge YAML if present
        # 3. Clamp/validate values
        # 4. Return immutable config
```

## Migration Path

### Phase 1 (Done)
- All production code switched to `ConfigSystem`
- Reflection scheduling and persona discussion use `ReflectionSettings`
- Old reflection config module and YAML files removed

### Phase 2 (Done)
- Removed `.env` parsing and environment variable overrides
- Configuration is now exclusively file-based

## Error Handling

- Missing `config.yaml`: Use defaults (silent)
- Invalid YAML syntax: Log warning, use defaults
- Invalid field values: Clamp to safe ranges with logging
- Missing required fields like API key: Use empty string, warn at runtime when needed

## Testing

- `ConfigSystem._test_config()` → heavily disabled/fast config
- `ConfigSystem._default_config()` → production defaults
- Tests can inject custom configs without file I/O
