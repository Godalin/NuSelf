# Configuration Spec

## Priority Hierarchy

| Priority | Source | Override Behavior |
|---|---|---|
| 1 (highest) | Process environment variables (`OPENAI_*`, `NUSELF_*`) | Wins over all lower layers |
| 2 | `.env` file at project root | Loads into `os.environ` only if key not already present |
| 3 | `private/config.yaml` | Overrides hardcoded defaults; silently ignored if missing or malformed |
| 4 (lowest) | Hardcoded defaults in `ConfigSystem._default_config()` | Safe production values |

**Key rule**: Env vars beat YAML beat defaults. The `.env` loader prefills `os.environ` without clobbering existing variables.

## Environment Variable Conventions

| Pattern | Example | Scope |
|---|---|---|
| `NUSELF_<DOTPATH_UPPER>` | `NUSELF_LLM_OPENAI_API_KEY` | General override for nested YAML path |
| `OPENAI_API_KEY` | `OPENAI_API_KEY` | Backward-compat; takes precedence over `NUSELF_LLM_OPENAI_API_KEY` |
| `OPENAI_BASE_URL` | `OPENAI_BASE_URL` | Backward-compat |
| `OPENAI_MODEL` | `OPENAI_MODEL` | Backward-compat |

**Type coercion**: `str` direct; `int` via `int()`; `float` via `float()`; `bool` accepts `true|yes|1|on` (case-insensitive).

## Config Sections

| Section | Dataclass | Purpose |
|---|---|---|
| `llm` | `LlmOpenAiConfig` | OpenAI-compatible endpoint |
| `chat` | `ChatContextConfig` | Context compression thresholds |
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

## Missing Config File Behavior

If `private/config.yaml` is missing, `ConfigSystem.load()` proceeds with defaults + env overrides. No error is raised.
