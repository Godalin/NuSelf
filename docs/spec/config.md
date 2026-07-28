# Configuration Spec

## Priority Hierarchy

| Priority | Source | Override Behavior |
|---|---|---|
| 1 (highest) | `private/config.yaml` | Overrides defaults; missing uses defaults and malformed/unreadable warns before fallback |
| 2 (lowest) | Hardcoded defaults in `ConfigSystem._default_config()` | Safe production values |

**Key rule**: YAML overrides hardcoded defaults. No other override mechanisms exist.

## Config Sections

| Section | Dataclass | Purpose |
|---|---|---|
| `llm` | `LlmConfig` | Ordered LLM endpoints and failover policy |
| `chat` | `ChatConfig` | Context compression thresholds, daemon request timeout, and language preference |
| `daemon` | `DaemonConfig` | Background task intervals |
| `reflection` | `ReflectionSettings` | Scheduling, gates, moderator |
| `email` | `EmailSmtpConfig` | SMTP settings |
| `macos_notification` | `MacosNotificationConfig` | macOS notifications toggle |
| `experimental` | `ExperimentalConfig` | Feature flags |

`experimental` currently contains only `vector_index`. The removed
`langmem_adapter` flag is not accepted by the editor-facing schema and does
not select an alternate memory-model runtime.

## JSON Schema

`docs/nuself-config.schema.json` is the editor-facing and external validation schema for `private/config.yaml`.

Rules:

- It must describe the same YAML shape as this spec and `ConfigSystem`.
- It is not the runtime parser; runtime behavior is still owned by `ConfigSystem`.
- Any configuration shape change must update the JSON Schema, `examples/private/config.yaml`, and config tests in the same change.
- Schema tests must cover at least the changed top-level shape so stale schema files are caught by CI.

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
- User-inspectable persona discussion text in logs, including participant notes, moderator notes, and synthesis summaries
- Reflection idea titles and bodies
- Notification texts derived from reflections

Internal prompts for memory curation, compression, routing, and structured decisions remain in English regardless of this setting. Persona discussion prompts may remain English, but their visible notes and summaries should ask the model to write in the configured language.

Supported values: any IETF language tag string (e.g. `en`, `zh-CN`, `zh-TW`). Default is `en`.

## Missing Config File Behavior

If `private/config.yaml` is missing, `ConfigSystem.load()` proceeds with hardcoded defaults. No error is raised.

Malformed YAML, invalid encoding, and expected file-read failures print one
concise warning and fall back to defaults. Unexpected exceptions are not
configuration fallback: they propagate so programming defects remain visible.
Callers must not wrap `ConfigSystem.load()` in a broad catch merely to recover
one default field.

## LLM Endpoint List And Failover

NuSelf supports multiple configured LLM endpoints for the same runtime.

Config shape:

```yaml
llm:
  - base_url: https://api.openai.com/v1
    api_key: ...
    model: gpt-4.1-mini
  - anthropic: true
    api_key: ...
    model: claude-sonnet-4-5
```

Rules:

- `llm` is an ordered list of endpoints. The first item is the default endpoint.
- Endpoints default to OpenAI-compatible behavior.
- If an endpoint has `anthropic: true`, NuSelf uses Anthropic Messages API semantics for that endpoint. `base_url` defaults to `https://api.anthropic.com/v1` when omitted.
- Each endpoint may set `timeout_seconds`. It controls the provider HTTP request timeout for that endpoint. If omitted, the default is 60 seconds.
- The old nested `llm.openai` shape is not part of v0.2.0. Configuration should use the direct `llm` list shape.
- If every configured endpoint has an empty API key, no LangChain endpoint is
  available. Chat returns its deterministic local configuration guidance;
  subsystems that require model generation fail clearly according to their own
  contract. NuSelf does not construct a local fallback LLM.
- Runtime LLM state is stored under `private/runtime/llm_state.json`.
- State records the last successful configured endpoint index in the `llm` list.
- On the next process use, NuSelf starts from the saved successful index, then wraps around through the configured endpoints.
- The state is a versioned derived preference record and is written through
  atomic file replacement. Its endpoint index must be a non-negative JSON
  integer; booleans are not integers for this contract.
- Missing state is the normal first-run case and silently uses configured
  endpoint order. Malformed, partial, unsupported, unreadable, or stale state
  emits a payload-safe `record_decode_failed` diagnostic and also uses
  configured endpoint order. Because this state is only a rebuildable
  preference, corruption must not prevent LLM use.
- The saved index is updated only after a successful request.
- When an endpoint fails with a provider-account availability error, NuSelf tries the next configured endpoint in the same request.
- Provider-account availability errors include HTTP 401, 402, 403, 429, and response bodies containing subscription, quota, billing, credit, or insufficient-balance indicators.
- Non-account errors, malformed responses, and prompt/protocol errors are not endpoint failover triggers unless explicitly classified later.
- Failover attempts are logged without exposing API keys.
- The `llm_endpoint_failed_over` log is emitted only when a later configured endpoint will actually be tried. If the failed endpoint is the last available endpoint, NuSelf logs `llm_endpoint_unavailable` with `status=exhausted` instead.

## Chat Daemon Request Timeout

`chat.request_timeout_seconds` controls how long CLI/REPL chat waits for the daemon to return one chat response.

Rules:

- The default is 120 seconds.
- This is a client-side daemon request timeout, not the provider HTTP timeout.
- Slow local models should raise this value and may also need a larger per-endpoint `llm[].timeout_seconds`.
- When this timeout is reached in the interactive REPL, the request is treated as a retryable transport failure according to the errors spec.
