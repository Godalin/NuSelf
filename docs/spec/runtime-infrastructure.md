# Shared Runtime Infrastructure Spec

## Purpose

NuSelf has several runtime boundaries: CLI commands, REPL commands, daemon
requests, agent tools, background workers, notifications, and structured logs.
They need shared infrastructure, but they do not all have the same delivery
semantics. The shared layer must make those semantics explicit instead of
building one untyped "message bus".

## Current Review Findings

The pre-infrastructure runtime has these recurring problems:

1. Daemon request dispatch is an `if request.type` chain while argparse and the
   REPL maintain separate registration conventions. Duplicate or missing
   handlers are detected only by tests or execution.
2. Daemon protocol payloads are generic dictionaries whose validation lives
   inside individual branches.
3. `write_log_event()` accepts free-form event/status strings and arbitrary
   metadata. There is no event identifier or schema version, and interactive
   deduplication hashes the complete serialized record.
4. The REPL repeatedly scans every log file to discover activity. Audit storage
   is therefore also acting as a slow cross-process activity feed.
5. Internal work uses unrelated transports: tuple queues, process-global
   callbacks, JSON dictionaries, log polling, and durable notification entries.
   Ownership, retry, and replay behavior differ but are not named in a common
   contract.
6. Some documentation still describes logs or the notification outbox as a
   generic event bus. Audit records and user notification delivery must not be
   treated as general command transports.

## Message Semantics

Every internal exchange belongs to exactly one of these categories:

| Category | Cardinality | Reply | Durability | Examples |
| --- | --- | --- | --- | --- |
| Request | one handler | required | transport-defined | daemon request, CLI command |
| Event | zero or more subscribers | none | optional projection | worker lifecycle, tool activity |
| Job | one worker at a time | completion state | required when retryable | reason export |
| Audit record | readers only | none | append-only | structured logs |
| Notification | adapter fan-out | delivery state | durable | outbox entry |

Code must not use an audit record as a command, a notification as a general
event, or an ephemeral event as the only record of retryable work.

## Handler Registry

`nuself.runtime.handlers.HandlerRegistry` is the shared in-process
request-dispatch primitive.

- A key maps to exactly one callable.
- Duplicate registration raises immediately.
- Registries are explicitly sealed after composition. Registration after
  sealing raises.
- Dispatch through an unregistered key raises `UnknownHandlerError`.
- A registry has no process-global singleton; the composition root owns it.
- Registries accept typed synchronous middleware during composition. Like
  handlers, middleware cannot be added after sealing.
- Middleware receives the handler key, the next callable, and the original
  typed arguments. It executes in registration order: the first middleware is
  outermost and the handler is innermost.
- Middleware may establish correlation, observation, authorization, or timing
  scopes, but it must not silently retry a request. Return values and
  exceptions propagate unchanged unless a boundary-specific middleware
  explicitly documents a translation.
- Transport adapters remain responsible for decoding requests and encoding
  responses. Business handlers do not read sockets or argparse internals.
- Boundary-specific exception handling wraps registry dispatch rather than
  being duplicated in each handler.

The daemon request registry must be complete for every declared
`RequestType`. CLI and REPL registries should migrate only where the shared
primitive improves ownership; argparse remains responsible for argument
parsing and LangChain remains responsible for agent tool dispatch.

Daemon dispatch installs one request-scope middleware. Every handler inherits
the daemon request id and `source="daemon"` through `RuntimeContext`, and log
activity projection is active for the complete handler invocation. Individual
handlers may add thread, turn, job, or trace fields through nested context
scopes. Unknown request mapping and unexpected exception-to-response encoding
remain daemon transport responsibilities outside the middleware pipeline.

## Daemon Payload Contracts

The JSONL transport retains `DaemonRequest` and `DaemonResponse` dictionaries
on the wire for protocol-version compatibility. Request handlers must decode
those dictionaries into request-specific frozen payload dataclasses before
using them, and construct response dictionaries through typed response payload
objects. Validation and defaulting belong to these codecs, not to handler
branches.

Request payload field sets are exact:

- `ping`, `health`, and `shutdown` accept only an empty object;
- `chat` requires string `message`, accepts optional non-blank string
  `thread_id` (default `default`) and optional non-blank string `turn_id`;
- `activity_open` requires non-blank string `turn_id`;
- `activity_next` requires non-blank string `subscription_id` and accepts
  optional integer `timeout_ms` (default 200, range 0..5000) and `limit`
  (default 50, range 1..256);
- `activity_close` requires non-blank string `subscription_id`.

Unknown payload fields are protocol errors. An omitted optional field receives
its documented default; a present field with the wrong type is never treated
as omitted. Payload codec `ProtocolError` values cross one daemon handler
boundary as failed responses rather than escaping dispatch. Rejection logging
is best effort and cannot replace that failed response.

`echo` is the deliberate exception: its contract is an arbitrary JSON object,
so passing its payload through unchanged is the typed behavior of that request.

Success response payload field sets are also exact:

- `ping` and `shutdown` return one string `message`;
- `health` returns `workers`, a list of complete typed worker-health records;
- `chat` returns string `answer`, `reply`, and non-blank `thread_id`, a string
  list `evidence_references`, nullable string `epistemic_status`, and optional
  numeric `confidence` and string `memory_update`;
- activity open/next/close return, respectively, non-blank
  `subscription_id`, a list of complete log-event records, and boolean
  `closed`.

Typed client operations own success-payload decoding. An explicit daemon
`error` response raises `DaemonApplicationError` and is not retryable as a
connection failure. An `ok` response with a malformed request-specific payload
raises `DaemonConnectionError` with the payload `ProtocolError` as its cause.
Nested worker and activity records fail the whole response; clients must not
skip malformed records or synthesize defaults.

### JSONL Transport Framing

The daemon transport is one request and one response per Unix-socket
connection. Every frame is UTF-8 JSON followed by exactly one newline and is
bounded by `MAX_DAEMON_FRAME_BYTES`, including that newline.

- A request envelope contains exactly `version`, `request_id`, `type`, and
  `payload`. A response envelope contains exactly `version`, `request_id`,
  `status`, `payload`, and an optional `error`.
- Duplicate object keys and unknown envelope fields are rejected rather than
  resolved by last-value-wins or silently ignored.
- Protocol versions are integers but never booleans. Request ids are
  non-blank strings.
- Payloads are recursive JSON values with string object keys. Non-finite
  numbers are invalid even when a JSON decoder would produce them from an
  overflowing exponent.
- An `ok` response has no `error`; an `error` response has a non-blank string
  `error`. These invariants apply equally to decoded peer frames and locally
  constructed frames at their encode boundary. The failed-response factory
  replaces a blank underlying diagnostic with a stable generic error.
- Server and client socket reads use the same bounded frame reader and byte
  limit.
- Empty EOF before any bytes is a quiet peer disconnect.
- EOF after partial bytes, a limit-length frame without newline, or bytes after
  the first newline are transport protocol errors.
- Server request reads use a finite IO timeout so a client cannot hold one
  request thread forever by withholding the newline.
- Client connect, send, and response-read operations share the caller's
  positive finite timeout.
- A decoded response must carry the request id sent on that connection.
- Malformed, oversized, incomplete, extra, or mismatched responses are exposed
  to callers as `DaemonConnectionError` with the protocol/transport error as
  cause.
- A client that disconnects before response delivery does not change an
  already-completed operation. The server records
  `daemon/response_delivery_failed` and returns from the connection handler
  without leaking the socket error.

## Runtime Envelope And Correlation Context

`nuself.runtime.context` owns `RuntimeContext`, `current_runtime_context()`,
and the nestable `runtime_context(...)` scope. The compatibility logging names
delegate to this neutral context; logging does not maintain a second context.

`nuself.runtime.messages.RuntimeEnvelope` is the versioned transport-neutral
envelope for events and jobs. It contains:

- stable message/event id;
- schema version;
- kind/name;
- producer component;
- creation timestamp;
- correlation fields (`request_id`, `turn_id`, `thread_id`, `job_id`,
  `trace_id`);
- JSON-safe typed payload.

Payload mappings and nested collections are frozen on construction. Consumers
receive immutable message data and `to_record()` returns a detached JSON-safe
copy for persistence or transport. `from_record()` is the symmetric strict
decoder for that version-1 wire shape; it rejects missing or unknown envelope
fields rather than guessing defaults.

Both locally constructed and decoded envelopes enforce the same invariants:

- `kind` is one of the declared message categories;
- `schema_version` is exactly the supported integer version, excluding
  booleans;
- message id, name, producer, and creation timestamp are non-blank strings;
- the creation timestamp is timezone-aware ISO-8601;
- context is a `RuntimeContext`, whose populated correlation values are
  non-blank strings;
- payload is a mapping with string keys and recursively JSON-safe values.

Payload keys are never coerced because coercion can collapse distinct keys.
Non-finite floats are not JSON values and are rejected. Decoded context and
payload containers are detached from the caller, and nested payload mappings
and sequences remain immutable inside the envelope.

Correlation context is inherited through one neutral runtime context. Logging
may project that context, but logging must not own it.

At an asynchronous message-consumption boundary, the consumer installs the
message's saved `RuntimeContext` as an exact replacement for the worker's
ambient context, then applies consumer-owned fields such as its worker
`source`. It must not merely merge into whatever context a reused worker thread
retained from a previous message. The prior worker context is restored after
each message on success, rejection, or failure.

Reason export `JobMessage` consumption additionally projects its durable
`resource_id` as `thread_id`. Initial queued messages retain the originating
request, turn, and trace fields. Retry messages created inside that activated
scope inherit the same chain and job id. Startup reconciliation messages have
no invented request identity but still carry their durable job/thread identity.
All logs emitted while inspecting, composing, failing, or retrying that job
therefore receive top-level correlation fields without relying on duplicated
metadata.

## Event Delivery

Ephemeral events use an in-process publisher/subscriber interface:

- publishing is synchronous by default so ordering and failures are explicit;
- subscribers are independently registered and cannot mutate the envelope;
- a logging subscriber may persist an audit projection;
- event delivery never performs hidden retries;
- cross-process live activity requires an explicit transport or cursor store,
  not repeated full-file scans presented as an event bus.

`nuself.runtime.events.EventPublisher` implements this boundary. Subscriptions
may target one event name or all events, preserve registration order, and are
removed through publisher-scoped opaque handles. Delivery continues across
subscriber failures and raises one `EventDeliveryError` containing every
failure after all matching subscribers have run.

Every published event resolves through a sealed
`EventDefinitionRegistry`. Core lifecycle definitions ship with the runtime;
domains extend them during composition through
`build_event_definition_registry(...)`. Duplicate definitions, late
registration, unknown names, and producer/name ownership mismatches fail before
delivery. Runtime event names use dotted subject/action names such as
`worker.started`; historical JSONL audit event slugs remain readable.

`runtime_event_log_sink(...)` is an optional subscriber. Its audit projection
preserves the original envelope ID; attaching it never changes event delivery
into log-driven control flow.

Events that can trigger durable or destructive state changes require a
request/job path with idempotency and explicit user approval. Replaying an
audit log must never repeat the action.

## Cross-Process Activity

Interactive daemon activity uses an explicit subscription transport over the
daemon JSONL request protocol:

1. the client opens a turn-scoped subscription before sending chat;
2. daemon request execution projects newly written `LogEvent` values to the
   request-scoped activity broker as well as the audit sink;
3. the client long-polls bounded batches while chat is running;
4. the client drains and closes the subscription after completion.

Subscriptions are bounded, expire when abandoned, and filter by `turn_id`.
They are display-only: receiving or replaying activity cannot execute a
command. Direct/one-shot mode may continue using the local incremental cursor;
daemon-attached REPL mode must not poll component log files for live activity.

## Durable Jobs

Retryable background work uses typed job records, not tuples:

- stable job id and job kind;
- owner/resource ids;
- attempt count and timestamps;
- explicit pending/running/completed/failed state;
- serialized payload and last error;
- idempotent worker claim/completion transitions.

The reason-output export queue is the first migration target. Its existing
durable manifest remains authoritative while the in-memory queue becomes a
typed wake-up mechanism rather than the job record itself.

`nuself.runtime.jobs.JobMessage` is that immutable wake-up contract. It carries
a versioned `kind="job"` envelope plus explicit `job_id` and `resource_id`.
Producers receive a `JobSink` through composition; domain modules must not
install process-global enqueue callbacks.

The durable job record is authoritative and queue delivery is a best-effort
wake-up. If wake-up delivery fails, the producer keeps the durable record,
reports the compact exception chain through the shared observability boundary,
and does not claim that the job was enqueued. Recovery may rediscover the
durable non-terminal record later.

## Logging

Structured logs are an append-only sink and read model.

- `LogEvent` will become a projection of the shared runtime envelope.
- Every newly written event has a stable id and schema version.
- Ephemeral runtime events and their producer ownership come from registered
  definitions. Their audit projections retain that registered dotted name.
  Direct domain audit writes use stable validated slugs governed by the
  owning domain spec rather than a process-global definition registry.
- Metadata must be JSON-safe before it reaches the sink.
- File writes are serialized per project/component.
- Readers use stable event ids and incremental cursors; complete-record hashing
  is a legacy compatibility fallback only.
- Existing JSONL records without ids/schema versions remain readable.

The UI, transcript exporter, and diagnostics may read logs. They must not use
log replay to execute domain actions.

`nuself.runtime.observability` owns the shared boundary for secondary effects
whose failure must be visible but must not alter an already-successful primary
operation. It records the failure through the structured log sink and falls
back to Python warnings only when that sink is unavailable. Domains must not
implement equivalent broad `try/except/pass` wrappers locally.

The caller may declare a narrower tuple of recoverable exception classes.
Only those failures are degraded; undeclared storage, programming, and
invariant failures continue to propagate. Omitting the tuple retains the
catch-all behavior for genuinely non-authoritative effects such as audit logs.

Persona consultation and discussion audit writes are secondary effects. Their
failure must not replace a successful persona result or mask the original
discussion failure. They use the shared boundary so failure reporting itself
cannot become a new authoritative failure.

Runtime behavior configured at composition time must be instance-scoped.
Callbacks such as reason-output section planners flow explicitly from the
daemon/chat composition root into the owning service. Domain modules must not
install process-global callback setters whose value can leak across projects,
tests, or concurrent runtimes.

## Owned Worker Lifecycle

`nuself.runtime.workers.OwnedWorker` owns one daemon thread and its lifecycle
state.

- Lifecycle states are `new`, `running`, `stopped`, and `timed_out`.
- `start()` is duplicate-safe and creates at most one thread for the owner's
  lifetime. A naturally exited or stopped worker is not implicitly restarted.
- The target wrapper records `stopped` in `finally`, including unexpected
  target exit.
- Daemon composition wraps each target in a supervisor that establishes its
  runtime source context and records any escaping `Exception` in daemon health.
  `OwnedWorker` itself remains domain-neutral and does not own logging.
- `join(timeout)` returns a typed snapshot. A live thread after the timeout is
  `timed_out`; later target exit transitions it to `stopped`.
- The primitive does not own domain intervals, retries, queues, timers, or the
  daemon-wide shutdown event.
- Daemon health reads liveness from owned workers rather than parallel thread
  fields. Domain success/error counters remain separate health data.
- Scheduled daemon workers share one iteration boundary for success/failure
  health transitions and observable error reporting. Reporting failure cannot
  terminate the loop; the shutdown-aware interval remains the only retry
  boundary.
- Export queue/timer cancellation remains an explicit export-worker cleanup
  performed before join.

## Daemon Instance Ownership

Each project root has at most one daemon owner. Before reading, deleting,
creating, or binding daemon socket/PID resources, `run_daemon()` must acquire a
non-blocking exclusive process lock on
`private/runtime/nuself.lock`. The lock file is a stable coordination inode and
is not deleted during normal cleanup.

The owner holds the lock until request serving and all background-worker
shutdown are complete. Only that owner may:

- remove a stale `nuself.sock` before binding;
- publish `nuself.pid`;
- remove the socket and PID during cleanup.

While holding that ownership, the daemon temporarily owns the process SIGINT
and SIGTERM handlers through `DaemonSignalOwner`. It restores pre-existing
handlers before project storage/socket/PID cleanup completes and before the
instance lock is released. Handler installation and restoration are explicit
lifecycle operations, not permanent module-level side effects.

If the lock is already held, the contender writes
`daemon/instance_lock_contended`, returns a non-zero exit status, and must not
construct daemon state or modify socket/PID resources. Unix-server binding must
complete before background workers start. Any bind or partial-start failure
still runs every owner cleanup step before the lock is released. Cleanup
failures are named and aggregated without discarding the bind/serve failure.
The daemon resets only the current project root's default storage backend;
other in-process project backends are not part of its ownership.

### PID Metadata

The lock owner publishes `private/runtime/nuself.pid` through atomic text-file
replacement. A valid PID record is one positive base-10 integer; surrounding
whitespace is ignored.

Missing PID state is the normal stopped/starting boundary and returns no PID
without a diagnostic. Empty, non-integer, zero, or negative content is corrupt
derived lifecycle metadata: readers emit a payload-safe
`record_decode_failed` event and return no PID. Non-missing filesystem failures
such as permission errors remain authoritative IO failures and propagate.

## Migration Order

1. Add and test the shared handler registry; migrate daemon request dispatch.
2. Centralize CLI handler binding/dispatch typing without replacing argparse.
3. Introduce runtime envelope and neutral correlation context.
4. Adapt structured logging into an envelope sink and add event ids, versions,
   serialized writes, and incremental cursors.
5. Introduce typed internal jobs and migrate reason export queue/callbacks.
6. Add an explicit event publisher for live in-process activity; retain
   cross-process compatibility until a dedicated transport is implemented.

Each migration must preserve external CLI/daemon protocol behavior unless its
governing spec and changelog explicitly describe a change.
