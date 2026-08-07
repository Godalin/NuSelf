# Logging Spec

## LogEvent Structure

`nuself.log.record` owns the immutable `LogEvent` projection model and
its record codec. It depends only on neutral runtime identity, JSON, and audit
types; protocol, domain-audit, and presentation code that handles an already
constructed event must not import filesystem log persistence.

The `nuself.log` package owns logging infrastructure without a package-root
facade: `record` owns the immutable projection, `store` owns JSONL paths and
append/rotation/recovery, `reader` owns readers and cursors, and `warning` owns
terminal-warning contracts. Callers import the precise owner they use.

| Field         | Type                                        | Required |
| ------------- | ------------------------------------------- | -------- |
| `time`        | `str` (ISO)                                 | yes      |
| `level`       | `"debug" \| "info" \| "warning" \| "error"` | yes      |
| `component`   | `LogComponent`                              | yes      |
| `event`       | `str` (slug)                                | yes      |
| `message`     | `str`                                       | yes      |
| `event_id`    | `str`                                       | new records |
| `schema_version` | `int`                                    | new records |
| `conversation_id` | `str \| None`                          | no       |
| `reason_id`   | `str \| None`                               | no       |
| `request_id`  | `str \| None`                               | no       |
| `turn_id`     | `str \| None`                               | no       |
| `job_id`      | `str \| None`                               | no       |
| `trace_id`    | `str \| None`                               | no       |
| `source`      | `str \| None`                               | no       |
| `node`        | `str \| None`                               | no       |
| `duration_ms` | `int \| None`                               | no       |
| `status`      | `str \| None`                               | no       |
| `error`       | `str \| None`                               | no       |
| `metadata`    | `Mapping[str, JSON value] \| None`          | no       |

Serialization (`to_record()`) omits `None`-valued optional fields.

Metadata is validated and recursively frozen when a `LogEvent` is constructed.
Mappings require string keys, floats must be finite, and arbitrary objects are
rejected rather than stringified. Nested mappings become immutable mappings and
lists/tuples become immutable tuples. Construction detaches from caller-owned
containers; `to_record()` returns a separate ordinary JSON-safe dict/list tree.
The audit sink, process-local observers, and live activity queues therefore
observe one stable event snapshot.

## Log Context

`LogEvent` is append-only evidence. The authoritative ephemeral correlation
state and its complete public API live in `nuself.runtime.context`.
`nuself.log.store` consumes the active `RuntimeContext`; it does not define logging-
specific context types, accessors, aliases, or state.

Runtime code may establish a `runtime_context(...)` around a daemon request,
chat turn, background job, or trace-producing operation.
`write_log_event(...)` inherits unset ownership fields from the current
runtime context:

- `conversation_id` for persistent conversation ownership;
- `reason_id` for long-running reason ownership;
- `request_id` for daemon/client request ownership;
- `turn_id` for one logical chat turn;
- `job_id` for daemon background jobs such as memory, reflection, Delivery, or future log maintenance;
- `trace_id` for cross-service provenance;
- `source` for the runtime boundary that wrote the event, such as `daemon`, `client`, or `chat_runtime`.

Every scheduled memory-curator, reflection, reason, and Delivery
tick owns a fresh `job_id`. Its worker source and job id are installed before
domain code runs; nested domain context adds fields without replacing that tick
identity. Iteration failure logs use the same job id, and reused worker threads
restore their ambient context before the next tick.

Explicit arguments to `write_log_event(...)` override the inherited context for that one event. Context must be reset when the request/turn/job exits; persisted `LogEvent` records are not mutated or deleted as part of context teardown.

Daemon lifecycle audit records are projected through the shared
`nuself.daemon.audit` boundary. A failed sink writes the shared
`observability_projection_failed` diagnostic with the intended event in
`metadata.failed_event`; it cannot alter the lifecycle decision that the
record describes.

Successful CLI lifecycle completion records describe the authoritative typed
transition result. Start and stop completion metadata includes `outcome`,
`changed`, `from_phase`, and `to_phase`. Restart has one requested record and
one completed record containing both stop and start outcomes and phase
boundaries. An idempotent start or stop is still a completed request, but its
outcome is `already_ready` or `already_stopped` and `changed=false`; it must not
masquerade as a newly performed transition.

Daemon lifecycle audit event names form a closed set owned by an immutable
definition registry in `daemon.audit`. Each definition owns the persisted
message, level, status, whether an error is required, and one exact metadata
schema. Producers supply only the event name plus schema data; they cannot
override projection defaults locally. Unknown events, missing or extra metadata
fields, incorrect field types, forbidden errors, and missing required errors
are programming errors raised before the best-effort log sink boundary.

Exact metadata field-set validation is one shared audit-definition primitive;
domain validators compose it with their own value constraints. Domains retain
separate sealed registries, messages, producers, and semantic validators.
Audit events without a current production producer are not retained as
speculative API surface.

Registered failure producers select the domain definition, fixed message, and
schema metadata. One shared observability interpreter derives the sanitized
exception chain, validates the selected definition, and invokes the
best-effort failure sink. Domains must not duplicate those mechanics or lose
control of event selection and metadata construction to a generic event bus.

`restart_failed` is one event with two explicit metadata variants selected by
`stage`: the `start` variant carries start-failure reason/phase/PID/socket/exit
code, while the `stop` variant carries stop-failure
reason/phase/PID/socket/owner-active state. No mixed variant is valid.

## Service Call Logs

When one subsystem invokes another subsystem through an agent-facing service/tool boundary, write a caller-owned log event with a service tag in metadata.

Example: chat calling a memory service tool writes a `chat` component event:

```json
{"component":"chat","event":"service_tool_called","metadata":{"service_component":"memory","tool":"memory_archive","args":{"entry_id":"m1"},"result":"Archived \"Old memory\"."}}
```

Human-readable rendering must show both tags at the front:

```text
[chat] [memory] service_tool_called tool=memory_archive status=completed
  args: {"entry_id": "m1"}
  result: Archived "Old memory".
```

Agent tools declared with `@observed` publish privacy-safe lifecycle through
the live `tool.activity` event: one `started` activity and exactly one
`completed` or `failed` activity. They do not duplicate that lifecycle under a
parallel `feature.*` name. Structured invocation arguments and results belong
only to the framework-owned `service_tool_called` outcome below. A tool may add
the orthogonal `@compact` declaration for presentation metadata; compactness is
never inferred from `@observed` and must not change the returned value or
observation cardinality.

Rules:

- The first tag is the caller component and determines the log file.
- The second tag is `metadata.service_component` and names the service being called.
- `service_tool_called` is an outcome event, not an invocation-intent event. It
  is emitted exactly once from the framework middleware's immutable completed
  `ToolOutcome`; decorators and tool implementations must not emit it.
- One shared tool-outcome projection owns the exact event message, status,
  top-level error, and metadata shape for both live logs and persisted
  snapshots. Callers provide only the caller component, resolved service
  component, and `ToolOutcome`.
- A successful outcome has `status="completed"`, no top-level error, and
  metadata containing exactly `service_component`, `tool`, `args`, and
  `result`. A failed outcome has `status="failed"`, the same error at the
  top-level and in metadata, and metadata containing exactly
  `service_component`, `tool`, `args`, and `error`.
- Tool names and service components must be non-empty strings. Arguments must
  be a JSON-compatible mapping frozen by `ToolOutcome`; result and error must
  be non-empty strings.
- `service_component` is a display tag, not a normal `key=value` header field.
- Human-readable tool-call headers show `tool=...` before `status=...`; both fields are highlighted when color is enabled.
- Agent-facing chat tools for memory, reflection, reason, trace, and selves all write `chat/service_tool_called` with the corresponding service tag.
- `selves_consult` also emits ordinary `persona` component logs for internal persona activity. The service-tool log records that chat called the selves service; the `persona` logs record what the selves service did.
- All other log formatting rules remain unchanged.
- Tool/service call I/O is structured metadata, not formatted message text:
  - `metadata.args` stores the structured tool arguments.
  - `metadata.result` stores the structured result when available, otherwise the result text.
  - `metadata.error` stores the error text when the call failed.
- The log `message` for newly written `service_tool_called` events is the fixed
  non-display value `Service tool outcome recorded`. Renderers display tool I/O
  from structured metadata; for persisted pre-structured snapshots, renderers
  may normalize the legacy `args:` / `result:` / `error:` message body into the
  same display path so historical reason steps remain inspectable.
- Renderers should use the same JSON block renderer for `args` and `result`, pretty-print JSON objects and arrays with the opening `{` or `[` on the section header line, expand JSON strings that contain nested JSON, and indent ordinary text consistently.

### Service Tag Rendering

The log event itself is the single source of truth for the service tag. When a tool is invoked, the wrapper writes the `service_component` directly into `metadata`. No code derives the service tag from the tool name at render time.

All rendering of tool call log events must read `metadata.service_component` from the log event — never guess it from the tool name.

Rules:

- The caller resolves the correct `service_component` from framework tool
  metadata. The shared outcome projection validates it and writes it into the
  event metadata; neither writer nor renderer infers it from the tool name.
- The renderer (`_render_service_tool_called`) reads `metadata.service_component` directly. It must NOT re-derive the service from the tool name.
- No subsystem stores a separate tool-call cache on domain objects. The log event is the record of a tool invocation. Any code that needs to display a past tool call queries the log system.

## Local REPL Command Diagnostics

Recoverable local command boundaries write ordinary structured events:

| Component | Event                              | Required metadata |
| --------- | ---------------------------------- | ----------------- |
| `persona` | `interactive_command_failed`       | `action`          |
| `chat`    | `interactive_history_load_failed`  | `conversation_id` |

The persona `action` is the first command token, or `list` for an empty
command. It must not contain the persona prompt, full command body, or other
arguments. The history diagnostic may contain the thread ID but not stored
message content. Both events use `status=error` and retain the compact
exception chain in the structured `error` field.

## LLM Response Diagnostics

Endpoint retry, failover, exhaustion/local-fallback, and final-response events
are observable projections of model control flow. A structured-log failure
uses the shared terminal-warning fallback and cannot change endpoint order,
consume or skip an attempt, prevent local fallback, or invalidate an accepted
response. Persisting the last successful endpoint is also a derived preference:
its failure is reported as `llm_endpoint_state_write_failed` without discarding
the response.

`chat/compression_fallback` is a warning with `status=degraded`, required safe
error diagnostics, and no metadata. It means optional model compression failed
and the persisted thread used the deterministic local summary. The event never
contains conversation text, the previous summary, prompts, model output, or
endpoint identity.

Shared per-endpoint availability diagnostics are owned by one sealed agent
endpoint audit registry for the `chat`, `memory`, `persona`, `reasoning`, and
`reflection` components:

| Event | Fixed level | Fixed status | Exact metadata |
|---|---|---|---|
| `llm_endpoint_failed_over` | `warning` | `failed_over` | `endpoint_index`, `model` |
| `llm_endpoint_unavailable` | `warning` | `exhausted` | `endpoint_index`, `model` |

Both events require a redacted structured error. Their messages are fixed by
the registry adapter. Endpoint URLs and API keys are forbidden. These records
describe one failed endpoint and remain distinct from caller-owned retry,
aggregate exhaustion, and fallback events.

Direct Chat diagnostics are owned by a sealed Chat audit registry. LLM retry
records may retain a non-negative configured endpoint index and model name,
but never the endpoint base URL. Client retry records use the standard
`request_id` field and never duplicate the previous exception text in
metadata.

| Event family | Fixed status | Exact metadata |
|---|---|---|
| `daemon_chat_completed`, `one_shot_chat_completed` | `ok` | none |
| `daemon_chat_failed`, `one_shot_chat_failed` | `error` | required error, no metadata |
| `final_response_completed` | `completed` | optional normalized `epistemic_status` |
| `llm_endpoint_retry` | `retry` | `endpoint_index`, `model` |
| `llm_retry_suppressed_after_tool_call` | `fallback` | `endpoint_index`, `model` |
| `llm_endpoints_exhausted` | `fallback` | required error, no metadata |
| `llm_endpoint_state_write_failed` | `degraded` | required error, `endpoint_index` |
| `interactive_history_load_failed` | `error` | required error, `conversation_id` |
| `interactive_history_write_failed` | `degraded` | required error, no metadata |
| Chat `completion_load_failed` | `degraded` | required error, exact `completion` kind |
| `interactive_prompt_failed` | `degraded` | required error, fixed fallback kind |
| `turn_retry` | `retry` | attempt bounds, failure phase, possible-completion flag |
| `activity_transport_degraded` | `degraded` | stage, error kind, optional connection decision fields and subscription-presence flag |
| `interactive_send_failed` | `error` | required error, no metadata |
| `interactive_cleanup_failed` | `error` | required error, ordered step names and primary-failure flag |

Messages are fixed operational descriptions. User messages, assistant
responses, tool arguments/results, endpoint URLs, previous exception text,
subscription ids, and duplicated request ids are forbidden in these metadata
schemas.

Reason owns a separate `reasoning/completion_load_failed` event with
`level=warning`, `status=degraded`, a required error, and no metadata. Its
identity already states that Reason thread completions failed, so it must not
duplicate a `reason_threads` completion kind.

## Chat Turn Logs

Every chat turn publishes registered lifecycle events from the chat component;
the audit projection writes their log records:

| Event            | Status      | Meaning                                                                                      |
| ---------------- | ----------- | -------------------------------------------------------------------------------------------- |
| `turn.started`   | `started`   | Chat runtime accepted a logical user turn                                                    |
| `turn.completed` | `completed` | Chat runtime produced and saved a final response                                             |
| `turn.reused`    | `completed` | A repeated `turn_id` returned an already-saved assistant response                            |
| `turn.failed`    | `error`     | Chat runtime failed before producing a final response                                        |
| `turn_retry`     | `retry`     | The interactive client is retrying the same logical turn after a retryable transport failure |

Rules:

- `turn.started` and `turn.completed` use the same `conversation_id` and, when available, the same top-level `turn_id`.
- `turn.completed` includes `duration_ms` and compact metadata such as `node_trace` and `tool_call_count`.
- `turn_retry` is a client-side transport retry marker. It must reuse the same `turn_id` and does not mean the daemon should persist a second user message.
- `turn_retry` metadata retains the previous client failure phase, daemon
  request id when allocated, whether that request may already have completed,
  the next attempt number, and the maximum attempt count.
- `activity_transport_degraded` records `stage=open|poll|drain|close`,
  `subscription_id` when allocated, exception kind, and for
  `DaemonConnectionError` its phase, request id, retryability, and
  possible-completion state.
- `interactive_send_failed` records an unexpected `Exception` escaping the
  bound send callback. Process-control `BaseException` values are re-raised and
  are not projected as ordinary chat failures.
- `interactive_cleanup_failed` records the ordered failed cleanup step names
  and whether the main loop already had a primary failure. It never replaces
  the structured interactive lifecycle error.
- `turn.reused` confirms idempotency: the retry returned an existing completed result instead of rerunning chat/tools.
- Final response boundary retries use `final_response_retry`; they are model-output retries inside one chat turn, not transport retries.
- Interactive logs should show chat lifecycle and retry events so users can distinguish normal multi-tool execution from retry-driven repeated work.
- Interactive log streaming must track already-seen event identities, not offsets into the timestamp-sorted global event list. Delayed daemon writes or concurrent background logs must not replay old turn events into the current REPL output.
- `InteractiveLogCursor.mark_seen(...)` lets a non-file transport register
  delivered identities. Daemon activity subscription batches use it before
  presentation so a later file fallback returns only events not already
  delivered.
- Chat service-tool logs should include the active `conversation_id` and, when available, the logical top-level `turn_id` so a tool call can be tied back to one chat turn.
- Approval-gated tools publish `chat/tool.activity` with
  `frontend_event=approval_requested` before asking the injected approval port,
  then publish `frontend_event=approval_decided`. The same runtime envelope is
  projected to the terminal, daemon activity transport, durable logs, or a
  future web frontend; no separate approval-log protocol exists.
- Approval metadata includes the service component, operation, safe summary,
  boolean decision, and input kind. It never carries arbitrary tool arguments
  or results.

Observed runtime-event publication treats only projection delivery failure as
a best-effort projection failure. If one or more projections fail, all matching
projections are still attempted, the structured delivery diagnostic is
best-effort, and the already-created envelope remains the publication result.
Event-definition, producer, envelope, and payload validation failures occur
before delivery and propagate to the producer; they must not be mislabeled or
suppressed as projection failures.

Unfiltered runtime log sinks deliberately receive every registered event.
Filtered `EventPublisher` projections must bind the complete registered
`(producer, name)` identity; event name alone is not an ownership boundary.

Core runtime events that project into logs use one shared typed payload
contract. The only fields are `message`, `level`, `node`, `duration_ms`,
`status`, `error`, and `metadata`; unknown fields are rejected rather than
silently ignored. Present scalar fields have their exact documented types,
duration is a non-negative integer, metadata is a mapping, and the complete
payload remains strict JSON. Core event definitions validate this contract
before the envelope is created or any projection runs. Chat/worker producers
and `write_runtime_event()` use the same payload type, so producer and sink
validation cannot drift. Extension event definitions may supply a different
validator when their payload is not a log projection.

## Process-Local Projection

`project_log_events(projection)` adds one bounded synchronous process-local
projection for the current execution context. It is separate from
`RuntimeContext`: projections are callable delivery effects, not serializable
correlation identity. This is not a general event observer API. Network calls,
unbounded waits, retries, and independently progressing effects require an
owned bounded transport instead.

- A non-callable projection fails at scope composition before any log is
  written.
- Nested scopes compose in outer-to-inner attachment order and restore the
  previous projection set on exit.
- The audit record is written before projections run.
- Each scope attachment has a distinct identity. During nested log writes, an
  attachment already active anywhere in the current delivery chain is skipped.
  Other attached projections still receive the nested record in order. This
  prevents direct and mutual recursive projection loops without conflating two
  scopes that intentionally attach the same callable.
- Each projection is best effort. One projection failure cannot suppress later
  projections, undo the audit write, or fail the business operation that
  logged.
- Best-effort isolation covers ordinary `Exception` values. A non-`Exception`
  `BaseException` remains process-control state: active-delivery identity is
  restored and the control object propagates after the durable append.
- Projection failures produce the historical best-effort
  `daemon/log_observer_failed`
  diagnostic with observation temporarily suspended. Logging core owns this
  event in a sealed infrastructure audit registry: the message is fixed, the
  level is `warning`, the status is `error`, the error is required, and
  metadata is forbidden. Callable names and exception type names are not
  persisted. Diagnostic failure is reported once as a `RuntimeWarning`
  containing both the observer failure and structured-log failure. The warning
  is the terminal fallback: it does not recurse, retry, or escape into the
  business operation, including when process warning policy promotes runtime
  warnings to errors.
- Projection failure records and terminal warnings use the shared safe diagnostic
  formatter for each exception. Broken exception renderers cannot replace the
  audit result, and credential-like values are removed before persistence or
  warning emission.
- Projections are not implicitly copied to new threads. A future deferred path
  that genuinely continues the same live projection must bind that effect
  explicitly; long-lived workers must establish their own ownership.

## Logging-Core Terminal Warnings

Logging core owns one sealed terminal-warning registry for failures that cannot
safely write another structured log. It contains exactly:

| Warning | Exact ordered fields | Fixed suffix |
|---|---|---|
| `logs/lock_cleanup_failed` | `component`, `operation`, `error_type` | none |
| `logs/append_rollback_failed` | `component`, `error_type` | none |
| `logs/rotation_failed` | `component`, `error_type` | retention bounds are not guaranteed |
| `daemon/log_observer_failed` | `observer_error`, `log_error` | none |
| `logs/corrupt_records_skipped` | `component`, `file`, `count`, `first_error` | none |
| `logs/event_identity_conflict` | `count`, `first_component`, `first_event` | none |

Definitions validate exact fields and domain values before rendering. One
canonical renderer fixes field order, rejects booleans as counts, and applies
credential redaction to the complete warning. Exception messages enter only
through fail-safe diagnostic formatting; corrupt-record warnings no longer call
an exception renderer directly. Registry or render failure must remain inside
the existing non-raising terminal warning boundary and must not trigger a
structured-log write.

Every persisted audit is a diagnostic projection. At the single runtime
envelope-to-`LogEvent` boundary, credential-like text is removed from
`message`, `error`, and recursively from metadata. Sensitive metadata keys are
replaced wholesale. Non-credential domain content remains unchanged, and the
caller's containers plus original runtime envelope remain immutable and
unmodified. Process-local observers receive the same sanitized `LogEvent` that
is written to disk.

## Log Components

| Component    | File             | Responsibility                                                       |
| ------------ | ---------------- | -------------------------------------------------------------------- |
| `daemon`     | `daemon.log`     | Daemon lifecycle                                                     |
| `chat`       | `chat.log`       | Conversation turns                                                   |
| `memory`     | `memory.log`     | Memory operations                                                    |
| `persona`    | `persona.log`    | Persona activations, host decisions, competitive persona discussions |
| `inbox`      | `inbox.log`      | User-attention item persistence and lifecycle                         |
| `delivery`   | `delivery.log`   | External Inbox delivery attempts                                     |
| `reflection` | `reflection.log` | Reflection scheduling                                                |
| `reasoning`  | `reasoning.log`  | Long-run reasoning threads                                           |
| `storage`    | `storage.log`    | Shared persistence lifecycle and backend infrastructure              |

Component log paths are reserved exclusively for canonical `LogEvent` JSONL.
Subsystems must not append ad-hoc text, tracebacks, or process stdout/stderr to
those files. Background daemon stdout/stderr uses the separate owner-only raw
stream `<authority-root>/logs/daemon-process.log`; it is crash diagnostic output, is not
read by `read_log_events()`, and does not participate in component retention,
observer delivery, or structured-log durability guarantees. Before each daemon
spawn, the owner rotates this raw stream when it has reached 5 MiB and retains
three numbered backups. Rotation happens before the child inherits its
descriptor; a single long-running daemon may exceed the threshold until its
next start. Rotation failure emits one content-safe terminal warning and cannot
block daemon startup. Daemon lifecycle owns a sealed one-event warning registry:
`daemon/process_log_rotation_failed` has exact `error_type` metadata and the
fixed suffix `continuing startup`. It contains no exception message, path, or
process-log content.

Display name mapping: `persona` → `selves`.

## Write Contract

- Every new write validates its component against `LOG_COMPONENTS`.
- Direct audit event names are stable lowercase slugs. Each segment starts
  with a letter and contains lowercase letters, digits, or underscores;
  registered runtime-event projections may join such segments with dots.
- A direct audit slug is one underscore-capable segment and therefore never
  contains a dot. A runtime-event projection contains at least two
  dot-separated segments. Runtime producers use one segment under the same
  grammar. These lexical rules have one shared implementation and are enforced
  for new records and definitions.
- Ephemeral runtime event names and producer ownership remain governed by
  `EventDefinitionRegistry` before publication. Direct append-only domain
  audit slugs are not forced into one process-global registry: their semantics
  remain governed by the owning domain specification and the shared lexical
  contract.
- JSON Lines format (`sort_keys=True`, `ensure_ascii=True`) encoded as UTF-8.
- Active records use an unbuffered binary append handle so short writes and
  record-boundary rollback remain explicit.
- Directory creation before open.
- New writes project a version-1 `RuntimeEnvelope`, including its stable
  `message_id` as `event_id`.
- The projected `schema_version` identifies the shared envelope/record wire
  shape, not the domain meaning of `event`. Breaking audit semantics use a new
  stable event slug; breaking runtime-event semantics use a new registered
  runtime event name. Existing persisted names are not repurposed or rewritten.
- A direct audit envelope carries the complete `RuntimeLogEventPayload`; its
  message, level, node, duration, status, error, and metadata survive envelope
  record round trips. An empty audit envelope is not a valid direct write.
- `create_audit_envelope(...)` constructs that self-contained immutable
  message. `write_audit_envelope(...)` and runtime-event projection share one
  envelope-to-`LogEvent` boundary, differing only in the required envelope
  kind. `write_log_event(...)` is the domain-facing convenience composition of
  those two audit operations.
- Authoritative log persistence uses `write_log_event(...)` directly.
Auxiliary evidence uses
  `write_observed_log_event(...)`, which mirrors the typed fields, returns the
  event or `None`, constructs and freezes one audit envelope before the
  best-effort persistence boundary, never retries or reconstructs the original
  record, and reports persistence failure as a distinct
  `observability_projection_failed` record with exact `failed_event` metadata.
- If any `report_observed_failure` structured write fails, its terminal
  fallback is the fixed `runtime/observability_sink_failed` warning. Exact
  fields retain the failed audit component/event plus the observed and sink
  error chains. A caller-specific `{component}/{event}` string is not reused as
  the warning identity.
- An `EventPublisher` may attach `runtime_event_log_sink(...)`; this bounded
  synchronous projection
  retains the published event's ID and correlation context.
- Writes are serialized by a per-path process lock and an advisory file lock;
  one complete JSON line is flushed before releasing the locks.
- Returns the constructed `LogEvent`.

## Read Contract

- `component=None` reads all component files; otherwise reads exactly one.
- Missing file → silently skip.
- All events sorted ascending by `time` (global chronological order).
- Structured timestamps must parse as timezone-aware ISO-8601 instants.
  Naive, malformed, and empty structured timestamps are corrupt records.
  Different offsets representing the same or differently ordered instants are
  compared as datetimes, never as raw strings; equal instants retain stable
  input order. Only the synthetic wrapper for a non-JSON plain legacy line may
  use `time=""`, and that sentinel sorts before timestamped records.
- `tail > 0` returns `events[-tail:]`.
- Non-JSON lines wrapped as `event="legacy"`.
- Invalid JSON lines skipped.
- Records predating the envelope fields remain readable with `event_id=None`
  and `schema_version=None`.
- Legacy absence means both `event_id` and `schema_version` are missing or
  null. If either identity field is present, both must be present and valid:
  `event_id` is non-blank and `schema_version` is exactly the supported integer
  version, excluding booleans. A partial identity pair is corrupt, not legacy.
- Every present optional scalar retains its declared type; invalid context,
  node, duration, status, error, or metadata values invalidate that record
  rather than being silently coerced to `None`. Duration is a non-negative
  integer and metadata remains strict JSON. The reader isolates the invalid
  line and continues with healthy and genuinely legacy records.
- Each full-reader file scan and each incremental file batch emits at most one
  terminal `RuntimeWarning` when structured records are isolated. The warning
  contains only the component, basename, skipped count, and first schema error
  type/message. It never contains the raw line, arbitrary record values,
  metadata, or an absolute path, and it never writes another structured log.
  Multiple corrupt records in the same batch are aggregated. Warning policy or
  hooks cannot make the read fail. Non-JSON legacy text remains readable and
  does not produce a corruption diagnostic.
- `InteractiveLogCursor` starts at the current byte length of each component
  file, reads only newly appended complete lines, and retains an incomplete
  trailing line for the next read. Stable event IDs provide deduplication;
  canonical record content is used only for legacy records.
- Full and incremental reads reconcile identities after chronological sorting.
  The first record for an identity is canonical. A later identical canonical
  record with the same identity is an expected overlap and is silently
  deduplicated, including across rotated/active files or activity transport
  plus file fallback. The cursor retains canonical fingerprints across batches
  and `mark_seen(...)`.
- Reusing an `event_id` for different canonical record content is an integrity
  conflict. The later record is suppressed and one non-raising terminal
  warning is aggregated per reconciliation batch. The warning contains only
  the conflict count plus first component/event name; it excludes event IDs,
  record payloads, messages, metadata, and paths. Legacy records continue to
  use canonical content-derived identity, so identical legacy copies dedupe.

## Log Retention And Rotation

Structured component logs use `LogRetentionPolicy`. The production default is
10 MiB per active file with three numbered backups.

- Rotation occurs before an append that would exceed `max_bytes`.
- The logs directory, active JSONL files, numbered backups, and stable lock
  sidecars are NuSelf-owned private runtime state. Opening them creates or
  hardens directories to `0700` and files to `0600`; append and rotation never
  widen those modes.
- `component.log.1` is the newest backup; older backups shift upward and the
  oldest backup beyond `backup_count` is deleted.
- A stable sidecar advisory lock serializes rotation and append across
  processes; locking the active inode itself is insufficient because rotation
  replaces that inode. The sidecar is not unlinked after a write: its stable
  path-to-inode identity must remain valid for processes that already have it
  open.
- The supplementary process-local lock registry uses normalized paths as keys
  and weak lock values. Active holders and waiters keep one shared lock alive;
  once no operation references it, the registry may reclaim both the lock and
  its path key. A long-lived process therefore does not retain every project
  path it has ever logged to.
- Opening the sidecar and acquiring its exclusive lock are authoritative
  prerequisites and their failures propagate before append. Unlocking or
  closing that sidecar occurs after the append outcome is known and is
  secondary: either failure emits a separate non-raising terminal warning but
  cannot turn a persisted event into a failed write or replace an append
  exception. The warning contains only component, cleanup operation, and
  exception type; it excludes event content, paths, and exception messages.
- Rotation is bounded-retention maintenance, not a prerequisite for event
  persistence. An `OSError` while deleting or replacing rotation files does
  not reject the current event: the writer appends it to whichever active file
  exists after the failed attempt, creating a new active file when the prior
  one was already moved. It emits one non-raising terminal warning containing
  only the component and exception type, never event content, filesystem
  paths, or the exception message. Lock acquisition, directory creation, and
  active-file append failures still propagate.
- A record append captures the active file length under the stable lock and
  writes the encoded JSONL record to completion, including retrying short
  writes, then `fsync`s the active file. The logs directory is synchronized
  before every record append, covering a newly created active name, rotation
  changes, and retry after a prior directory-sync failure. If writing or
  synchronization fails, the writer truncates back to the captured boundary
  and `fsync`s that rollback before propagating the original error. The failed
  event is not delivered to observers. If truncate or rollback synchronization
  fails, one non-raising terminal warning reports only component plus rollback
  exception type; it never replaces the primary append error or includes event
  content, paths, or exception messages.
- Directory synchronization is identity-aware, not record-batched. A bounded
  process-local cache remembers only successfully synchronized active
  `(device, inode)` identities. Repeated appends to the same active inode skip
  redundant directory `fsync`; first use, rotation, cross-process replacement,
  and retry after synchronization failure must synchronize again. Cache
  eviction only causes an extra safe sync.
- The synchronous public API does not use implicit batching, group commit, a
  timer, or an asynchronous flush worker. Each returned `LogEvent` still owns
  one complete data-file write, `fsync`, close, and observer outcome.
- A successful data-handle close after append synchronization completes the
  durable append contract. Process-local observers run only afterward. A close
  failure propagates as `LogAppendLifecycleError`; the event is not delivered
  to observers even though its persistence outcome is `persisted`.
- `LogAppendLifecycleError` retains the append `primary_error`, rollback error,
  and close error independently, plus a `persistence_outcome` of
  `not_persisted`, `persisted`, or `uncertain`. The append error is its explicit
  cause when present, otherwise the close error is. A failed rollback makes the
  outcome `uncertain`; successful append synchronization makes it `persisted`;
  successful rollback synchronization makes it `not_persisted`. A failed
  append followed by successful rollback keeps the original append exception
  unchanged when close succeeds.
- Readers include numbered backups in chronological sorting.
- Incremental cursors track file identity as well as byte offset. If rotation
  replaces the active file, a cursor finishes the matching `.1` inode from its
  old offset before reading the new active file from byte zero.
- Legacy and active files remain append-only within one file generation.
