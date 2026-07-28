# Logging Spec

## LogEvent Structure

| Field         | Type                                        | Required |
| ------------- | ------------------------------------------- | -------- |
| `time`        | `str` (ISO)                                 | yes      |
| `level`       | `"debug" \| "info" \| "warning" \| "error"` | yes      |
| `component`   | `LogComponent`                              | yes      |
| `event`       | `str` (slug)                                | yes      |
| `message`     | `str`                                       | yes      |
| `event_id`    | `str`                                       | new records |
| `schema_version` | `int`                                    | new records |
| `thread_id`   | `str \| None`                               | no       |
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
`nuself.logs` consumes the active `RuntimeContext`; it does not define logging-
specific context types, accessors, aliases, or state.

Runtime code may establish a `runtime_context(...)` around a daemon request,
chat turn, background job, or trace-producing operation.
`write_log_event(...)` inherits unset ownership fields from the current
runtime context:

- `thread_id` for conversation thread ownership;
- `request_id` for daemon/client request ownership;
- `turn_id` for one logical chat turn;
- `job_id` for daemon background jobs such as memory, reflection, notification, or future log maintenance;
- `trace_id` for cross-service provenance;
- `source` for the runtime boundary that wrote the event, such as `daemon`, `client`, or `chat_runtime`.

Every scheduled memory-curator, reflection, reason, and notification-delivery
tick owns a fresh `job_id`. Its worker source and job id are installed before
domain code runs; nested domain context adds fields without replacing that tick
identity. Iteration failure logs use the same job id, and reused worker threads
restore their ambient context before the next tick.

Explicit arguments to `write_log_event(...)` override the inherited context for that one event. Context must be reset when the request/turn/job exits; persisted `LogEvent` records are not mutated or deleted as part of context teardown.

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

Rules:

- The first tag is the caller component and determines the log file.
- The second tag is `metadata.service_component` and names the service being called.
- `service_component` is a display tag, not a normal `key=value` header field.
- Human-readable tool-call headers show `tool=...` before `status=...`; both fields are highlighted when color is enabled.
- Agent-facing chat tools for memory, reflection, reason, trace, and selves all write `chat/service_tool_called` with the corresponding service tag.
- `selves_consult` also emits ordinary `persona` component logs for internal persona activity. The service-tool log records that chat called the selves service; the `persona` logs record what the selves service did.
- All other log formatting rules remain unchanged.
- Tool/service call I/O is structured metadata, not formatted message text:
  - `metadata.args` stores the structured tool arguments.
  - `metadata.result` stores the structured result when available, otherwise the result text.
  - `metadata.error` stores the error text when the call failed.
- The log `message` for newly written `service_tool_called` events is not a display body. Renderers display tool I/O from structured metadata; for persisted pre-structured snapshots, renderers may normalize the legacy `args:` / `result:` / `error:` message body into the same display path so historical reason steps remain inspectable.
- Renderers should use the same JSON block renderer for `args` and `result`, pretty-print JSON objects and arrays with the opening `{` or `[` on the section header line, expand JSON strings that contain nested JSON, and indent ordinary text consistently.

### Service Tag Rendering

The log event itself is the single source of truth for the service tag. When a tool is invoked, the wrapper writes the `service_component` directly into `metadata`. No code derives the service tag from the tool name at render time.

All rendering of tool call log events must read `metadata.service_component` from the log event — never guess it from the tool name.

Rules:

- The writer (log callback) is responsible for determining the correct `service_component` and writing it into the log event's `metadata`. The writer may use any approach (e.g. consulting tool metadata, a naming convention, or an explicit tag on the tool object).
- The renderer (`_render_service_tool_called`) reads `metadata.service_component` directly. It must NOT re-derive the service from the tool name.
- No subsystem stores a separate tool-call cache on domain objects. The log event is the record of a tool invocation. Any code that needs to display a past tool call queries the log system.

## Chat Turn Logs

Every chat turn publishes registered lifecycle events from the chat component;
the audit subscriber writes their log projections:

| Event            | Status      | Meaning                                                                                      |
| ---------------- | ----------- | -------------------------------------------------------------------------------------------- |
| `turn.started`   | `started`   | Chat runtime accepted a logical user turn                                                    |
| `turn.completed` | `completed` | Chat runtime produced and saved a final response                                             |
| `turn.reused`    | `completed` | A repeated `turn_id` returned an already-saved assistant response                            |
| `turn.failed`    | `error`     | Chat runtime failed before producing a final response                                        |
| `turn_retry`     | `retry`     | The interactive client is retrying the same logical turn after a retryable transport failure |

Rules:

- `turn.started` and `turn.completed` use the same `thread_id` and, when available, the same top-level `turn_id`.
- `turn.completed` includes `duration_ms` and compact metadata such as `node_trace` and `tool_call_count`.
- `turn_retry` is a client-side transport retry marker. It must reuse the same `turn_id` and does not mean the daemon should persist a second user message.
- `turn.reused` confirms idempotency: the retry returned an existing completed result instead of rerunning chat/tools.
- Final response boundary retries use `final_response_retry`; they are model-output retries inside one chat turn, not transport retries.
- Interactive logs should show chat lifecycle and retry events so users can distinguish normal multi-tool execution from retry-driven repeated work.
- Interactive log streaming must track already-seen event identities, not offsets into the timestamp-sorted global event list. Delayed daemon writes or concurrent background logs must not replay old turn events into the current REPL output.
- Chat service-tool logs should include the active `thread_id` and, when available, the logical top-level `turn_id` so a tool call can be tied back to one chat turn.
- Approval-gated tool execution writes an `approval_prompted` event before waiting for confirmation. The live REPL treats it as user-relevant interactive activity so the visible prompt appears before input is read.

## Process-Local Observation

`observe_log_events(observer)` adds a synchronous process-local projection for
the current execution context. It is separate from `RuntimeContext`: observers
are callable delivery effects, not serializable correlation identity.

- Nested scopes compose in outer-to-inner registration order and restore the
  previous observer set on exit.
- The audit record is written before observers run.
- Each observer is best effort. One observer failure cannot suppress later
  observers, undo the audit write, or fail the business operation that logged.
- Observer failures produce a best-effort `daemon/log_observer_failed`
  diagnostic with observation temporarily suspended. Diagnostic failure is
  swallowed, so observer errors cannot recurse or escape into the business
  operation.
- Observers are not implicitly copied to new threads. A future deferred path
  that genuinely continues the same live projection must bind that effect
  explicitly; long-lived workers must establish their own ownership.

## Log Components

| Component    | File             | Responsibility                                                       |
| ------------ | ---------------- | -------------------------------------------------------------------- |
| `daemon`     | `daemon.log`     | Daemon lifecycle                                                     |
| `chat`       | `chat.log`       | Conversation turns                                                   |
| `memory`     | `memory.log`     | Memory operations                                                    |
| `persona`    | `persona.log`    | Persona activations, host decisions, competitive persona discussions |
| `outbox`     | `outbox.log`     | Notification delivery attempts                                       |
| `reflection` | `reflection.log` | Reflection scheduling                                                |
| `reasoning`  | `reasoning.log`  | Long-run reasoning threads                                           |
| `storage`    | `storage.log`    | Shared persistence lifecycle and backend infrastructure              |

Display name mapping: `persona` → `selves`.

## Write Contract

- Every new write validates its component against `LOG_COMPONENTS`.
- Direct audit event names are stable lowercase slugs. Each segment starts
  with a letter and contains lowercase letters, digits, or underscores;
  registered runtime-event projections may join such segments with dots.
- Ephemeral runtime event names and producer ownership remain governed by
  `EventDefinitionRegistry` before publication. Direct append-only domain
  audit slugs are not forced into one process-global registry: their semantics
  remain governed by the owning domain specification and the shared lexical
  contract.
- JSON Lines format (`sort_keys=True`, `ensure_ascii=True`).
- Append mode (`"a"`, `encoding="utf-8"`).
- Directory creation before open.
- New writes project a version-1 `RuntimeEnvelope`, including its stable
  `message_id` as `event_id`.
- An `EventPublisher` may attach `runtime_event_log_sink(...)`; this projection
  retains the published event's ID and correlation context.
- Writes are serialized by a per-path process lock and an advisory file lock;
  one complete JSON line is flushed before releasing the locks.
- Returns the constructed `LogEvent`.

## Read Contract

- `component=None` reads all component files; otherwise reads exactly one.
- Missing file → silently skip.
- All events sorted ascending by `time` (global chronological order).
- `tail > 0` returns `events[-tail:]`.
- Non-JSON lines wrapped as `event="legacy"`.
- Invalid JSON lines skipped.
- Records predating the envelope fields remain readable with `event_id=None`
  and `schema_version=None`.
- `InteractiveLogCursor` starts at the current byte length of each component
  file, reads only newly appended complete lines, and retains an incomplete
  trailing line for the next read. Stable event IDs provide deduplication;
  canonical record content is used only for legacy records.

## Log Retention And Rotation

Structured component logs use `LogRetentionPolicy`. The production default is
10 MiB per active file with three numbered backups.

- Rotation occurs before an append that would exceed `max_bytes`.
- `component.log.1` is the newest backup; older backups shift upward and the
  oldest backup beyond `backup_count` is deleted.
- A stable sidecar advisory lock serializes rotation and append across
  processes; locking the active inode itself is insufficient because rotation
  replaces that inode.
- Readers include numbered backups in chronological sorting.
- Incremental cursors track file identity as well as byte offset. If rotation
  replaces the active file, a cursor finishes the matching `.1` inode from its
  old offset before reading the new active file from byte zero.
- Legacy and active files remain append-only within one file generation.
