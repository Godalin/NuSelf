# Configuration Spec

## Priority Hierarchy

| Priority | Source | Override Behavior |
|---|---|---|
| 1 (highest) | Selected workspace `.nuself/config.yaml` | Recursively overrides user configuration in explicit workspace scope |
| 2 | User authority `config.yaml` | Overrides built-in defaults in every scope |
| 3 (lowest) | Hardcoded defaults in `ConfigSystem._default_config()` | Safe production values |

The final merged mapping is validated once. Sequences and scalar values replace
the lower layer; mappings merge recursively. Scope selection and the strict
separation between layered configuration and single-authority state are
governed by [`scope.md`](scope.md).

## Config Sections

| Section | Dataclass | Purpose |
|---|---|---|
| `llm` | `LlmConfig` | Ordered LLM endpoints and failover policy |
| `chat` | `ChatConfig` | Context compression thresholds, daemon request timeout, and language preference |
| `daemon` | `DaemonConfig` | Background task intervals |
| `reflection` | `ReflectionSettings` | Scheduling, gates, moderator |
| `email` | `EmailConfig` | SMTP delivery settings |
| `macos_notification` | `MacosNotificationConfig` | macOS notifications toggle |
| `experimental` | `ExperimentalConfig` | Feature flags |

`experimental` currently contains only `vector_index`. The removed
`langmem_adapter` flag is not accepted by the editor-facing schema and does
not select an alternate memory-model runtime.

## JSON Schema

`docs/nuself-config.schema.json` is the editor-facing and external validation
schema for every authority's `config.yaml`.

Rules:

- It must describe the same YAML shape as this spec and `ConfigSystem`.
- It is not the runtime parser; runtime behavior is still owned by `ConfigSystem`.
- Any configuration shape change must update the JSON Schema, `examples/.nuself/config.yaml`, and config tests in the same change.
- Schema tests must cover at least the changed top-level shape so stale schema files are caught by CI.
- Schema tests must select the validator from the schema's declared dialect,
  check the schema itself, and compare runtime and published-schema acceptance
  for shared constraints.

All runtime configuration models are strict and reject IEEE non-finite numbers
(`NaN`, positive infinity, and negative infinity). Timeout values must be
finite and at least their documented minimum before reaching daemon or
provider clients.

## Runtime Paths

The default user authority is `~/.nuself`, optionally replaced by
`NUSELF_HOME`. Explicit workspace scope uses `<workspace>/.nuself`. Both use
the layout and resolution contract in [`scope.md`](scope.md).

The resolved runtime-path object names the structured `daemon.log`; the daemon
process log separately owns raw stdout/stderr. Runtime directory creation is
explicit and limited to the selected managed authority.

## Language Preference

`chat.language_preference` controls the language of user-facing LLM outputs:
- Chat agent responses (including persona-synthesized and tool follow-up replies)
- User-inspectable persona discussion text in logs, including participant notes, moderator notes, and synthesis summaries
- Reflection idea titles and bodies
- Notification texts derived from reflections

Internal prompts for memory curation, compression, routing, and structured decisions remain in English regardless of this setting. Persona discussion prompts may remain English, but their visible notes and summaries should ask the model to write in the configured language.

Supported values: any IETF language tag string (e.g. `en`, `zh-CN`, `zh-TW`). Default is `en`.

## Missing Config File Behavior

If a configuration layer is missing, loading proceeds with lower layers. No
error is raised.

Single-file loads memoize validated immutable configuration by path, mtime, and
size. A changed file replaces stale entries automatically, while a missing file
is never cached so later creation is discovered. There is no explicit cache
reset API without a runtime reload use case; daemon configuration remains fixed
until restart.

`nuself dev health` does not report a missing config file as unhealthy.
`nuself dev config` describes the effective file/default state and explicitly
states that a running daemon must be restarted after configuration changes.
The daemon freezes its effective configuration and adapter plan at startup;
the disk projection is not presented as a live daemon reload.

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
- If an endpoint has `anthropic: true`, NuSelf uses Anthropic Messages API
  semantics for that endpoint. `base_url` defaults to
  `https://api.anthropic.com` when omitted. Configuration may use either the
  API root or its trailing `/v1` prefix; NuSelf removes exactly one terminal
  `/v1` before passing the root to the Anthropic SDK because that SDK appends
  `/v1/messages` itself.
- NuSelf explicitly disables Anthropic extended thinking at the provider
  adapter. Framework-native structured output forces a tool choice, while the
  Anthropic protocol forbids forced tool choice in thinking mode. This is a
  runtime-contract requirement, not model-name inference.
- Provider selection is explicit configuration. NuSelf does not infer
  OpenAI-compatible versus Anthropic semantics from a model name or endpoint
  URL; gateways that expose different models through different protocols must
  set `anthropic` per endpoint.
- Each endpoint may set `timeout_seconds`. It controls the provider HTTP request timeout for that endpoint. If omitted, the default is 60 seconds.
- The LLM composition boundary exposes one endpoint builder from typed
  `LLMSettings`. Runtime configuration and opt-in live matrix tests use that
  same builder so provider selection, timeout, retry, and temperature behavior
  cannot drift.
- The old nested `llm.openai` shape is not part of v0.2.0. Configuration should use the direct `llm` list shape.
- If every configured endpoint has an empty API key, no LangChain endpoint is
  available. Chat returns its deterministic local configuration guidance;
  subsystems that require model generation fail clearly according to their own
  contract. NuSelf does not construct a local fallback LLM.
- Runtime LLM state is stored under the selected authority's
  `runtime/llm_state.json`.
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
- When an endpoint fails with a typed or structurally identified provider
  availability error, NuSelf tries the next configured endpoint in the same
  request.
- Provider availability errors include provider authentication, permission,
  payment, rate-limit, connection, and timeout exception types, plus structured
  HTTP status codes 401, 402, 403, and 429.
- Provider exception messages and response bodies are diagnostic material, not
  failover classification inputs.
- Non-account errors, malformed responses, and prompt/protocol errors are not endpoint failover triggers unless explicitly classified later.
- Endpoint failover observations are owned by one sealed agent endpoint audit
  registry. Only the `chat`, `memory`, `persona`, `reasoning`, and `reflection`
  components may emit them.
- `llm_endpoint_failed_over` is emitted with `status=failed_over` only when a
  later configured endpoint will actually be tried.
- `llm_endpoint_unavailable` is emitted with `status=exhausted` when the failed
  endpoint is the last available endpoint. It is a per-endpoint observation;
  the capability owner retains its separate aggregate exhaustion or fallback
  contract.
- Both endpoint events are warnings, require a redacted error, and have exact
  metadata `{endpoint_index, model}`. The index is a non-negative integer and
  the model is a non-blank string.
- Endpoint audit metadata never contains API keys, endpoint base URLs, prompts,
  responses, or raw provider exception text.

`nuself dev config` is a safe effective-configuration projection. It prints
only flattened scalar leaf values plus explicit derived fields. Secret leaves,
including every endpoint API key and SMTP password, are redacted. A field name
containing `password`, `token`, `secret`, or `credential`, plus `api_key`, is
always treated as sensitive. The projection must not retain
or print aggregate dictionaries, lists, model dumps, or parent container
values that can bypass leaf-level redaction.

In-memory endpoint settings also exclude API keys from `repr`. Test failures,
debuggers, container representations, and incidental object formatting must
not reveal a credential merely because they render an endpoint object.

All runtime configuration models are frozen, type-strict, reject unknown
fields, and hide input values in validation errors. YAML must decode to an
object; `llm` must use the public endpoint-list shape. Quoted numbers and
booleans are not coerced, booleans are not accepted as integers, and integers
are not accepted as booleans. Wrong top-level shapes, obsolete nested LLM
objects, unknown fields, and invalid values fail explicitly rather than being
silently discarded.

The runtime loader accepts only the current schema. It does not remove,
translate, warn about, or otherwise normalize retired configuration fields;
unknown v0.2.5 fields such as `experimental.langmem_adapter` fail strict
validation. One-time migrations belong in repository scripts rather than the
installed runtime.

Before reading a present `<authority-root>/config.yaml`, NuSelf hardens the
managed authority root to `0700`, rejects non-regular files and symlinks, and
hardens the config file to `0600`. Managed directory creation and hardening use
no-follow directory handles: the authority root and every managed descendant
must be an actual directory, never a symlink or another file type. Rejection
occurs before changing the redirected target's permissions or contents.
Secret values are never read from a permissive or redirected file.

## Email Delivery

Email uses the selected authority's `config.yaml`. The obsolete
`private/email.toml` path is not read. Enabled email is validated solely from
the current YAML fields; missing required values produce the same input-hidden
Pydantic validation error as any other invalid current configuration.

When `email.enabled` is true, `email.smtp.host`, `email.from_address`, and
`email.to_address` must be non-empty. SMTP `username` and `password` must be
provided together; `port` is from 1 through 65535. Sender and recipient reject
header control characters. API keys and SMTP passwords are excluded from model
`repr`, and all validation diagnostics hide the rejected input.

The published JSON Schema describes the user-authored document before runtime
default merging. Enabled email may omit `smtp` entirely and receive the
runtime defaults; when supplied, its host must not be blank. The schema
enforces the same username/password pair, non-blank enabled addresses, and
header-control rejection as runtime validation. A maintained acceptance matrix
passes identical YAML objects to the real loader and a standards-compliant
JSON Schema validator and requires the same accept/reject result, in addition
to static field/default/range parity.

## Chat Daemon Request Timeout

`chat.request_timeout_seconds` controls how long CLI/REPL chat waits for the daemon to return one chat response.

Rules:

- The default is 120 seconds.
- This is a client-side daemon request timeout, not the provider HTTP timeout.
- Slow local models should raise this value and may also need a larger per-endpoint `llm[].timeout_seconds`.
- When this timeout is reached in the interactive REPL, the request is treated as a retryable transport failure according to the errors spec.
