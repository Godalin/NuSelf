# Configuration Spec

## Priority Hierarchy

| Priority | Source | Override Behavior |
|---|---|---|
| 1 (highest) | `private/config.yaml` | Overrides hardcoded defaults; silently ignored if missing or malformed |
| 2 (lowest) | Hardcoded defaults in `ConfigSystem._default_config()` | Safe production values |

**Key rule**: YAML overrides hardcoded defaults. No other override mechanisms exist.

## Config Sections

| Section | Dataclass | Purpose |
|---|---|---|
| `llm` | `LlmOpenAiConfig` | OpenAI-compatible endpoint |
| `chat` | `ChatConfig` | Context compression thresholds and language preference |
| `daemon` | `DaemonConfig` | Background task intervals |
| `reflection` | `ReflectionSettings` | Scheduling, gates, moderator |
| `email` | `EmailSmtpConfig` | SMTP settings |
| `macos_notification` | `MacosNotificationConfig` | macOS notifications toggle |
| `experimental` | `ExperimentalConfig` | Feature flags |

## Runtime Paths

```
<project_root>/
  private/
    runtime/          # PID, socket, cursors
    logs/             # *.log files
    outbox/           # notification entries
    memory/
      entries/        # MemoryEntry JSON files
      candidates/     # MemoryCandidate JSON files
    threads/          # ThreadState JSON files
    sources/
      documents/      # SourceDocument JSON files
      chunks/         # SourceChunk JSON files
    profile/items/    # ProfileItem JSON files
    config.yaml       # live user config
  examples/private/   # sample data for tests/demos
```

`runtime_paths(project_root)` resolves these. `ensure_runtime_dirs()` creates missing directories.

## Language Preference

`chat.language_preference` controls the language of user-facing LLM outputs:
- Chat agent responses (including persona-synthesized and tool follow-up replies)
- Reflection idea titles and bodies
- Notification texts derived from reflections

Internal prompts (persona discussions, memory curation, compression) remain in English regardless of this setting.

Supported values: any IETF language tag string (e.g. `en`, `zh-CN`, `zh-TW`). Default is `en`.

## Missing Config File Behavior

If `private/config.yaml` is missing, `ConfigSystem.load()` proceeds with hardcoded defaults. No error is raised.
