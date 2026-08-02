# Shared Runtime Infrastructure Spec

## Purpose

NuSelf has several runtime boundaries: CLI commands, REPL commands, daemon
requests, agent tools, background workers, notifications, and structured logs.
They need shared infrastructure, but they do not all have the same delivery
semantics. The shared layer must make those semantics explicit instead of
building one untyped "message bus".

## Historical Review Findings

The pre-infrastructure runtime had these recurring problems:

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
| Event | zero or more projections | none | optional projection | worker lifecycle, tool activity |
| Job | one worker at a time | completion state | required when retryable | reason export |
| Audit record | readers only | none | append-only | structured logs |
| Notification | adapter fan-out | delivery state | durable | outbox entry |

Code must not use an audit record as a command, a notification as a general
event, or an ephemeral event as the only record of retryable work.

## Frontend Event Boundary

Backend execution publishes presentation-worthy activity directly through the
existing typed `EventPublisher`. There is no parallel frontend-event model or
adapter bus. Terminal, daemon-stream, test, and future web adapters consume
runtime envelopes and decide how to render or transport them.

Backend features, services, repositories, agents, and workers must not import
`nuself.tui`, call `input()`, print presentation text, or depend on ANSI
rendering. They request interaction through typed ports and publish typed
events. The terminal adapter owns prompting and rendering; a web adapter may
translate the same requests and events to its own protocol.

Events cover operation lifecycle, model/tool activity, approval
requested/decided, warnings, recoverable degradation, and user-facing
progress. They contain stable identity, component, status, correlation
context, and payload-safe fields. Raw prompts, memories, credentials,
arbitrary arguments, and arbitrary return values are excluded by default.

Frontend publication is synchronous and best effort unless a caller explicitly
requires delivery. Durable audit projection subscribes separately; the
frontend feed must not tail log files.

## Decorated Execution Policies

Cross-cutting behavior is declared through independent immutable function
policies and interpreted by middleware. Identity, component, effects,
confirmation, observation, and audit are separate policies. Adding one policy
must not require a wrapper function or change a domain signature.

Policy decorators are inert declarations. Middleware owns ordering:
authorization and confirmation precede the operation; observation surrounds
it; audit projection follows the actual outcome. Approval port, event
publisher, clock, and audit sink are injected at composition. Feature policy
execution publishes its small typed payload directly; it must not create a
second frontend event wrapper around a runtime envelope. No policy may
discover a terminal or global runtime implicitly.

The decorated function remains directly callable in domain tests. Only an
application or tool adapter applies policies, preventing hidden business logic.

## Handler Registry

`nuself.runtime.handlers.HandlerRegistry` is the shared in-process
request-dispatch primitive.

- A key maps to exactly one callable.
- Handler and middleware objects are checked for callability at composition
  time, including middleware supplied to the registry constructor. Invalid
  components raise `TypeError` before sealing or dispatch.
- Duplicate registration raises immediately.
- A closed command catalog seals through
  `seal(expected_keys=...)`. Coverage is checked atomically before the
  dispatch table is published; missing or extra registrations raise typed
  `HandlerRegistryCoverageError` with immutable `missing` and `extra` key
  sets. Catalog owners must not repeat this comparison locally.
- Registries are explicitly sealed after composition. Registration after
  sealing raises.
- Dispatch through an unregistered key raises `UnknownHandlerError`.
- Concrete handler registry failures inherit `RuntimeError` directly. A common
  registry-error family is not part of the contract unless an independent
  caller policy needs to handle every registration and dispatch failure alike.
- A registry has no process-global singleton; the composition root owns it.
- Registries accept typed synchronous middleware during composition. Like
  handlers, middleware cannot be added after sealing.
- `resolve()` exposes a directly registered raw handler only before sealing for
  composition-time inspection. A sealed registry rejects raw resolution so
  runtime callers cannot bypass middleware; runtime invocation always uses
  `dispatch()`.
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
- A boundary may translate `UnknownHandlerError` only when registry lookup
  itself failed. With a sealed catalog, it checks key membership before
  invocation and must not catch that type around the handler call:
  middleware, nested registries, and handlers may raise the same exception,
  and invocation exceptions preserve their exact identity.

The daemon request registry must be complete for every declared
`RequestType`. CLI and REPL registries should migrate only where the shared
primitive improves ownership; argparse remains responsible for argument
parsing and LangChain remains responsible for agent tool dispatch.

The interactive REPL top-level command boundary uses the shared registry after
lexical command resolution:

- the declarative REPL command catalog is authoritative for canonical names,
  aliases, completion, and help;
- one resolver maps a complete input command to exactly one canonical name and
  argument body before dispatch;
- the CLI composition root owns one `ReplCommandDispatcher` and its sealed
  registry for the interactive session;
- every canonical catalog entry has exactly one registered handler, and
  composition fails when the catalog and registry differ;
- handlers receive the argument body plus an immutable command context
  containing the project root, current thread, and session;
- unknown input remains a presentation concern and renders interactive help
  without entering the registry.

Argparse remains responsible for parsing, but stores only a stable command key
in the parsed namespace. `CliHandlerBindings` owns a parser-local
`HandlerRegistry`, seals it after parser composition, and `dispatch_cli(...)`
performs the one-shot typed dispatch. LangChain continues owning agent-tool
dispatch and is not routed through `HandlerRegistry`.

Daemon dispatch installs one request-scope middleware. Every handler inherits
the daemon request id and `source="daemon"` through `RuntimeContext`, and log
activity projection is active for the complete handler invocation. Individual
handlers may add conversation, reason, turn, job, or trace fields through nested context
scopes. Unknown request mapping and unexpected exception-to-response encoding
remain daemon transport responsibilities outside the middleware pipeline.
Unsupported-request mapping is decided from the sealed registry key set before
dispatch. Once invocation starts, an `UnknownHandlerError` raised by the
request-scope middleware or business handler is not relabeled as an unsupported
daemon request.

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
  `conversation_id` (default `default`) and optional non-blank string `turn_id`;
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

Request envelope decode, request-payload decode, and registered handler
invocation are distinct exception sources:

- socket request-envelope `ProtocolError` becomes a malformed-request response
  before dispatch;
- request handlers wrap only their direct payload codec call as
  `DaemonRequestPayloadError`, which `handle_request(...)` translates into a
  rejected-request response and audit;
- a raw `ProtocolError` raised later by middleware, nested transport code, or
  business logic is an unexpected invocation failure. It preserves identity
  through the handler boundary and is handled by the socket adapter's generic
  invocation-failure path, not relabeled as malformed client payload.

Success response payload field sets are also exact:

- `ping` returns one non-blank `authority_id`; request type plus successful
  response status already express readiness and must not be duplicated as a
  fixed `pong` message;
- `shutdown` returns an exact empty object; request type plus successful
  response status already acknowledge shutdown and must not be duplicated as a
  fixed message;
- `health` returns the complete typed scheduler snapshot directly; the daemon
  has one scheduler authority and must not wrap it in a single-field health
  envelope;
- `chat` returns string `answer`, non-blank `conversation_id`, a string list
  `evidence_references`, nullable string `epistemic_status`, and optional numeric
  `confidence`; terminal adapters may name that answer `reply` in their local
  presentation result, but the wire does not duplicate it;
- activity open/next return, respectively, non-blank `subscription_id` and a
  list of complete log-event records; idempotent activity close returns the
  shared exact empty payload.

The daemon client exposes typed request operations for these protocol actions.
Raw request transport and generic successful-response decoding are internal
implementation details, not second public client APIs.

The in-process `ActivityBroker.close()` command mirrors that protocol: it is
idempotent and returns no status value. Callers verify absence through later
subscription operations rather than a test-only removal boolean.

The open response and close request share one exact subscription-identity
codec. Direction-specific wrappers around the same single field are prohibited;
next retains its separate request model because timeout and batch limit are
independent inputs.

Typed client operations own success-payload decoding. An explicit daemon
`error` response raises `DaemonApplicationError` and is not retryable as a
connection failure. An `ok` response with a malformed request-specific payload
raises `DaemonConnectionError` with the payload `ProtocolError` as its cause.
Nested worker and activity records fail the whole response; clients must not
skip malformed records or synthesize defaults.

## Unified Daemon Scheduler

The daemon owns one `DaemonScheduler`. It replaces subsystem-specific worker
threads, wake-up events, pending sets, admission queues, start locks, periodic
loops, and worker-health bookkeeping. Adding a daemon responsibility registers
one typed task handler; it must not add another long-lived worker abstraction.

The daemon composition object exposes the scheduler itself to transport
adapters instead of adding pass-through health or shutdown methods. Startup
remains a composition operation because it also prepares durable recovery and
recurring work; lifecycle cleanup shuts down the exposed sole scheduler
directly. Domain-specific admission methods remain private unless another
production boundary actually uses them. The request handler state protocol
contains only capabilities used by registered handlers; domain runtimes remain
private to daemon composition. The closed task-kind type is the single source
for the runtime task catalog; a second handwritten catalog is prohibited.

Recurring responsibilities are declared once as an immutable sequence of task
kind and interval pairs. Startup iterates that sequence; it must not mirror
individual intervals as mutable daemon-state attributes or repeat one submit
branch per task. Membership in this sequence is the sole periodic subset
catalog; it must not be repeated as another handwritten literal type.

Each in-memory task has a registered kind, stable identity, one primary
resource key, fixed priority, optional monotonic `run_at`, immutable runtime
context and payload, and one completion handle. Identity coalesces pending and
running duplicates by returning the existing completion handle; admission does
not allocate a second result wrapper or expose redundant admitted/coalesced
status. A busy resource prevents overlapping work on that resource without
allocating a resource lock.

The queue is a wake-up mechanism, never authoritative business state. Durable
state remains in SQLite, repositories, outboxes, or export manifests. Startup
recovery and periodic discovery may therefore submit the same identity safely.
A queue-capacity failure does not erase durable work; a later scan or restart
must rediscover it.

Capacity exhaustion and stopped admission are separate concrete scheduler
errors because callers handle both as recoverable wake-up deferral. They inherit
the standard runtime error directly; there is no broader scheduler-error family
without an independent consumer or policy.

One dispatcher owns admission state and a bounded executor performs handlers.
Scheduler lifecycle has one monotonic phase (`created`, `running`, `stopping`,
or `stopped`); running and admission health are derived from it rather than
stored as independent booleans. The busy-resource set is also the authoritative
in-flight set, so the scheduler does not maintain a second task count that can
drift from resource ownership. All scheduler state (pending tasks, active
identities, busy resources, delayed tasks, and lifecycle phase) is protected by
one short-held condition. No handler,
database operation, model call, file operation, event projection, audit write,
or approval prompt runs while that condition is held. Tasks declare one primary
resource; multi-record consistency remains a repository transaction concern.
When executor capacity is full, or every due task is blocked by a busy
resource, the dispatcher waits for a completion/admission/shutdown
notification. It must not repeatedly wait with a zero timeout. Timed waiting
considers only future tasks whose resources are currently available.

Control-plane requests (`ping`, `health`, `shutdown`, and activity subscription
operations) execute directly in the socket adapter. Work-plane requests such
as chat submit a task and wait on its completion handle. Slow model calls must
not prevent control-plane service. Socket request threads perform transport and
waiting only; they do not execute chat/domain work.

Periodic responsibilities are recurring scheduler admissions, not permanent
threads. The next occurrence is calculated after the current occurrence
completes, preventing overlapping or accumulated ticks. Discovery tasks may
submit resource-specific work, while domain state and retry policy remain
domain-owned.

Shutdown closes admission, wakes the dispatcher, cancels pending volatile
wake-ups, and waits within one daemon-wide graceful deadline for dispatched
work. Completion always releases task identity and resource in a `finally`
boundary. Durable unprocessed work is recovered at the next startup.
Work-plane requests fail closed unless the scheduler is running. Running is
derived from the `running` phase and therefore already implies admission is
accepting; daemon request threads never execute synchronous domain fallbacks.
After a chat turn and its durable memory observation commit, admission of
curation and compression is only a wake-up. Capacity or shutdown rejection is
observed as deferred work and cannot replace the successful reply. Periodic
discovery recovers pending observations and conversations still requiring
compression.

Scheduler health exposes only a payload-safe failure type and task kind. A
successful task clears current degradation, so an old failure is not presented
as ongoing health damage; raw exception messages never enter health payloads.

Runtime events remain observation only. Scheduler activity may publish typed
task lifecycle events; neither an event projection nor audit replay may submit
work. The scheduler API is intentionally limited to registration, admission,
scheduling, start, shutdown, and an immutable snapshot. It must not grow plugin
discovery, dependency graphs, event sourcing, dynamic policy engines, or a
persistent generic queue.

`DaemonState` composes scheduler handlers from the existing `ApplicationGraph`.
It does not own PID/socket files, instance locking, signal installation, server
timing, or lifecycle error aggregation. The only daemon-wide concurrency
primitives introduced here are the existing single-daemon instance lock and the
scheduler condition. Repository transactions, cross-process locks needed for
direct CLI coexistence, and the activity broker condition remain independent.

Behavior-identical blocking locks over NuSelf-managed resource files share the
dependency-neutral context primitive in `nuself.private_fs`. Conversation and
notification domains choose their own stable lock identity and mutation scope;
the shared primitive only hardens the lock file and owns blocking `flock`
acquisition and release. Non-blocking daemon ownership, schema migration,
append-log, and curator locks retain their separate contention and cleanup
contracts. There is no process-global lock registry or generic lock manager.

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
- Exceptions become failed responses only through the protocol-owned
  exception factory. It safely renders and sanitizes a single exception before
  assigning `error`; unexpected multi-layer failures use the shared sanitized
  compact-chain formatter. Local transport and handler code must not serialize
  exceptions with `str(...)`.
- Server and client socket reads use the same bounded frame reader and byte
  limit.
- Empty EOF before any bytes is a quiet peer disconnect.
- EOF after partial bytes, a limit-length frame without newline, or bytes after
  the first newline are transport protocol errors.
- Server request reads use a finite IO timeout so a client cannot hold one
  request thread forever by withholding the newline.
- Client connect, send, and response-read operations share the caller's
  positive finite timeout.
- The client calls the Unix socket `connect()` operation directly; it does not
  perform a racy path-existence preflight. Missing and stale socket paths are
  ordinary connect-phase `OSError` failures with their cause retained.
- A decoded response must carry the request id sent on that connection.
- Malformed, oversized, incomplete, extra, or mismatched responses are exposed
  to callers as `DaemonConnectionError` with the protocol/transport error as
  cause.
- Client connection errors retain the generated request id and one structural
  phase. Retryability and whether the daemon may already have executed the
  request are derived from that phase, rather than inferred from exception
  text. Typed payload decode happens after a valid response envelope and is
  non-retryable.
- A client that disconnects before response delivery does not change an
  already-completed operation. The server records
  `daemon/response_delivery_failed` and returns from the connection handler
  without leaking the socket error.
- Response encoding completes before the first socket write. An invalid or
  oversized decided response records `daemon/response_encode_failed` and is
  replaced by one stable bounded error frame with the same request id. The
  server does not substitute a frame after a write has begun; fallback or
  ordinary frame write/flush failure remains
  `daemon/response_delivery_failed`.

`nuself.daemon.socket_server` owns the Unix-socket transport adapter. Its
`NuSelfUnixServer` stores only the structural `DaemonRequestState`, whose
filesystem capability is the selected `authority_root`; its
`RequestHandler` reads one bounded frame, decodes one `DaemonRequest`, calls
the typed daemon request registry boundary, encodes one `DaemonResponse`, and
writes one bounded frame. The module must not import `DaemonState` or the
daemon process runner.

The daemon process entrypoint accepts explicit user-root and optional
workspace-root inputs from lifecycle startup. It reconstructs the selected
scope before opening `ApplicationRuntime`; it does not infer workspace scope
from an `.nuself` path or ambient current directory.

The socket adapter catches request-envelope `ProtocolError` only around
`DaemonRequest.from_json_line(...)`. Handler invocation has a separate
`Exception` boundary, so an invocation that happens to raise `ProtocolError`
is recorded as `request_failed` and cannot masquerade as envelope decode
failure.

`nuself.daemon.transport_audit` owns the socket adapter's sealed operational
failure schemas. `socket_server` supplies only the caught exception, event
identity, available request correlation, and exact schema metadata; it does
not construct log presentation.

Transport `ProtocolError` values become failed responses. Request-read
`OSError`, unexpected handler exceptions, response-encoding failures, and
response-delivery failures resolve through the sealed transport audit adapter.
A clean peer disconnect returns without a response. The daemon process runner owns
socket path creation, server-loop timing, state construction, signals, workers,
and cleanup; none of those responsibilities belong to the socket adapter.

Observed transport failures may attach the server state's project root as
non-authoritative diagnostic context. The handler resolves that hint through
an explicit `NuSelfUnixServer` ownership check: an unowned server adapter
returns no hint, while failures reading an owned structural state propagate
instead of being hidden by a broad exception catch. Authoritative request
dispatch continues to use the strict typed state accessor.

## Runtime Envelope And Correlation Context

`nuself.runtime.context` owns `RuntimeContext`, `current_runtime_context()`,
and the nestable `runtime_context(...)` scope. The compatibility logging names
delegate to this neutral context; logging does not maintain a second context.

`nuself.runtime.messages.RuntimeEnvelope` is the versioned transport-neutral
envelope for runtime events, typed job wake-ups, and audit identity
projections. Its complete supported kind taxonomy is `event | job | audit`.
Kinds are added only with a concrete producer, consumer, payload contract, and
ownership model; the decoder must reject placeholder or unimplemented kinds.
It contains:

- stable message/event id;
- schema version;
- kind/name;
- producer component;
- creation timestamp;
- correlation fields (`request_id`, `turn_id`, `conversation_id`, `reason_id`, `job_id`,
  `trace_id`);
- JSON-safe typed payload.

Runtime context records accept only those canonical correlation field names.
The former chat `thread_id` spelling is not decoded as an alias for
`conversation_id`; Reason-owned payloads may still use their distinct domain
`thread_id` field.

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

These are structural envelope invariants, not domain authorization. A decoded
envelope may still name an unknown event/job, use a disallowed producer, or
carry semantically invalid domain data. Event, job, and audit owners validate
those contracts through their own sealed definitions rather than teaching the
transport envelope every domain vocabulary.

The envelope `schema_version` versions only this transport-neutral wire shape.
It does not version the meaning of a runtime event name or its payload. A
compatible payload extension remains governed by that event's registered
validator. A breaking payload or semantic change requires a new event name;
it must not silently reuse an existing producer/name pair or bump the global
envelope version. The envelope version changes only when the common envelope
record itself requires a new decoder contract.

Payload keys are never coerced because coercion can collapse distinct keys.
Non-finite floats are not JSON values and are rejected. Decoded context and
payload containers are detached from the caller, and nested payload mappings
and sequences remain immutable inside the envelope.

Correlation context is inherited through one neutral runtime context. Logging
may project that context, but logging must not own it.

An `audit` envelope is self-contained: it carries the shared typed log payload
rather than using an empty envelope merely to allocate identity. Direct audit
and runtime-event envelopes use the same log projector, so serializing and
decoding an audit envelope preserves every field needed to append the same
`LogEvent`.

Daemon `request`/response frames are transport contracts owned by
`daemon.protocol`, including framing limits and response status; they are not
runtime envelopes. Notification intents are durable outbox records that embed
`RuntimeContext` directly and are likewise not runtime envelopes. Neither
ownership model is represented by a dormant envelope kind.

At an asynchronous message-consumption boundary, the consumer installs the
message's saved `RuntimeContext` as an exact replacement for the worker's
ambient context, then applies consumer-owned fields such as its worker
`source`. It must not merely merge into whatever context a reused worker thread
retained from a previous message. The prior worker context is restored after
each message on success, rejection, or failure.

Reason export `JobMessage` consumption additionally projects its durable
`resource_id` as `reason_id`. Initial queued messages retain the originating
request, turn, and trace fields. Retry messages created inside that activated
scope inherit the same chain and job id. Startup reconciliation messages have
no invented request identity but still carry their durable job/reason identity.
All logs emitted while inspecting, composing, failing, or retrying that job
therefore receive top-level correlation fields without relying on duplicated
metadata.

Durable domain queues may embed `RuntimeContext` directly when the durable
record itself is the authoritative intent. The notification outbox follows
this pattern and deliberately does not add a redundant `RuntimeEnvelope`.
Delivery installs the saved entry context per record under the notification
worker source, using the same exact replacement/restoration semantics.

Every scheduler task exactly installs its submitted correlation context and a
`source="daemon.task.<kind>"` value. Reason export additionally projects the
durable resource and job identities into that context. Success and failure both
restore the executor thread's prior context; reused slots never inherit the
previous task's correlation.
Production task construction has one closed-kind factory and one constructor
path: it captures the current context when no explicit durable context is
supplied, or stores the supplied context unchanged. These are values selected
before construction, not separate task shapes or compatibility paths.

## Client Chat Scope

Every daemon-backed or one-shot client chat operation establishes one nested
`RuntimeContext` containing its requested thread, optional turn ID, and
`source="client"`. It preserves any caller-owned request, job, and trace
identity, and restores the complete caller context on every return or
exception.

Client transport success/failure audits inherit that scope rather than
repeating correlation fields on each write. If a successful daemon response
names a different thread, only the completion projection may nest a narrower
thread override for the response-owned identity.

Each interactive retry attempt executes inside the same logical turn context,
including the `turn_retry` marker and the send callback. The retry marker must
not be written before entering that scope. All attempts reuse the same turn ID;
attempt scoping changes correlation ownership, not retry count or idempotency.

## Named Cleanup Execution

`nuself.runtime.cleanup` owns the domain-neutral cleanup execution primitive.
`run_cleanup_steps(...)` accepts an ordered sequence of `(step, operation)`
pairs, attempts every operation exactly once, and returns an ordered tuple of
`CleanupFailure(step, error)`. It catches `BaseException` so control failures
cannot bypass later cleanup or silently replace an earlier primary failure.

`cleanup_failure_records(...)` is the one audit-facing projection of that
tuple. It returns ordered `{step,error}` records using the canonical safe
exception chain, so lifecycle owners do not independently format nested
cleanup errors.

The cleanup utilities do not log, retry, raise, choose step order, or define a
lifecycle result. Daemon and REPL owners compose their own steps and retain
their domain-specific lifecycle error, diagnostic event, primary-cause, and
success rules.

## Owned Thread Context

`OwnedCall` captures Python's complete `Context` when the call is constructed.
Its owned thread executes the target inside that copied context, so the
authority-scoped application runtime, immutable `RuntimeContext`, and future
orthogonal `ContextVar` capabilities cross the one-shot thread boundary
together. The caller and worker contexts remain independent, and worker exit
or failure cannot mutate the initiating thread's context.

Ownership rules:

- synchronous `run_observed_best_effort` operations execute in their existing
  context and need no binding;
- the CLI live-chat send thread relies on its `OwnedCall` context capture so
  the chat turn and application authority continue across the thread boundary;
- that boundary transports ordinary callback `Exception` values back as
  observed interactive failures, but transports non-`Exception`
  `BaseException` values back as main-thread control flow after subscription
  cleanup;
- the CLI establishes an exact turn context before binding, so unrelated
  ambient request, job, or trace identity cannot leak into a new user turn;
- correlation inheritance does not itself grant presentation ownership:
  interactive sessions capture only activity allowed by the CLI visibility
  contract, even when other synchronous work inherits the same turn identity;
- daemon tasks carry an immutable captured context; the scheduler installs a
  task-owned source and never inherits dispatcher-thread state.

Implicit or blanket thread-context propagation is forbidden because it can
attach startup requests or previous operations to unrelated background work.

## Domain Execution Scopes

A domain operation must not create a parallel `ContextVar` for an identity
already represented by `RuntimeContext`. `ReasonAdvancer` establishes a nested
runtime scope whose `reason_id` is the active durable reason thread. It
preserves caller-owned request, turn, job, trace, and source fields, so manual
commands and scheduled ticks retain their causal chain while reason workspace
and persona tools resolve one authoritative thread identity.

The reason scope is restored after agent completion or failure. Tool providers
must fail clearly if invoked without an active reason thread rather than
reading process-global mutable state or guessing a workspace.

## Event Projection Delivery

Ephemeral events use an in-process publisher/projection interface:

- publishing is synchronous so projection ordering and completion are explicit;
- projections are independently attached and cannot mutate the envelope;
- a logging projection may persist an audit record;
- event delivery never performs hidden retries;
- cross-process live activity requires an explicit transport or cursor store,
  not repeated full-file scans presented as an event bus.

`nuself.runtime.event.publisher.EventPublisher` implements this boundary. This API is
not a general asynchronous event bus: every attached projection must be a
bounded in-process operation whose completion is intentionally part of
`publish()` completion. Network calls, unbounded waits, retries, notifications,
and other independently progressing effects require a separately owned bounded
queue and worker lifecycle; they must not be attached as projections merely to
reuse event routing.

Projections may target one complete event identity or all events, preserve
attachment order, and are detached through publisher-scoped opaque handles.
Each publisher creates one
non-address lifetime token and copies it into its handles; ownership checks
must not use `id(publisher)` or another identity that can be reused after the
publisher is destroyed. A handle from another or earlier publisher therefore
cannot detach a current projection, even if process memory addresses are
reused. Delivery continues across projection failures and raises one
`EventDeliveryError` containing every failure after all matching projections
have run; each failure carries the same lifetime-bound handle as the failed
attachment. Its compact message includes each projection exception type and
non-empty message so best-effort observability does not discard the actionable
failure cause.

Building `EventDeliveryError` is a reporting boundary: an exception whose
`__str__` fails must still remain in `failures`, and its type plus a stable
fallback must appear in the aggregate message. Diagnostic formatting must not
replace the projection failure set.

Each publication captures one ordered projection snapshot under the
publisher lock, then invokes callbacks without holding that lock. Attaching or
detaching a projection from a callback never changes the active snapshot: a
detached projection still receives the current event if it was present at
publication start, and a newly attached projection starts with the next
publication.
Mutations are visible to a nested publication started after the mutation.
Callbacks may therefore publish recursively without deadlocking the publisher.
The publisher, sealed definition registries, and handler registries use
non-reentrant state locks; callback and handler invocation must remain outside
those locks rather than relying on recursive acquisition.

Projections and optional event-definition payload validators must be callable
at composition time. Invalid projections fail in `attach_projection(...)`; invalid
validators fail while constructing the definition. They must not survive until
publication and be misreported as delivery or payload failures.

Every published event resolves through a sealed
`EventDefinitionRegistry`. Core lifecycle definitions ship with the runtime;
domains extend them during composition through
`build_event_definition_registry(...)`. Duplicate definitions, late
registration, unknown names, and producer/name ownership mismatches fail before
delivery. Runtime producers are lowercase slugs beginning with a letter and
containing only lowercase letters, digits, and underscores. Runtime event names
contain at least two dot-separated segments under the same slug grammar, such
as `task.started` or `reason.output.export`. Definitions reject invalid
identities at construction, before registry composition or publication.

A registered `(producer, name)` pair is an immutable semantic contract.
Renaming it or making its payload contract incompatible creates a new event
identity and coordinated producer/consumer migration. Historical JSONL audit
event slugs remain readable and are never rewritten merely because current
naming policy changes.

Definition storage mechanics have one owner:
`runtime.definitions.DefinitionRegistry`. It provides ordered registration,
duplicate rejection, explicit sealing, lookup, and immutable definition
snapshots for any hashable key. `EventDefinitionRegistry` is a semantic adapter
using `(producer, name)` keys; `AuditDefinitionRegistry` is the shared adapter
for direct persisted audits using `(component, event)` keys. Domains retain
their own identity taxonomies, metadata validators, and messages rather than
defining parallel registry or delivery mechanics. A domain instantiates one
sealed `AuditCatalog` from those declarations. The catalog owns definition
lookup plus the shared write, caught-failure, and best-effort execution paths;
it is not an event bus and never discovers handlers dynamically.

`resolve()` is a runtime operation and rejects an unsealed
`DefinitionRegistry`; composition code uses registration and immutable
definition snapshots instead. Domain adapters translate this state failure into
their typed unsealed-registry errors. Runtime owners must reject an unsealed
adapter during construction rather than retain a registry whose supported
identity set can change after the owner starts. `EventPublisher` applies this
check before accepting projections or publishing.

Runtime events and persisted audits remain distinct boundaries. Runtime events
are synchronous immutable-envelope publication to projections; lifecycle
audits are direct best-effort log projections with fixed presentation defaults.
Writing an audit never publishes an in-process event, publishing an event never
implicitly creates a lifecycle audit except through an explicitly attached log
projection, and replaying persisted records never invokes projections.

Each publication validates exactly once against the recursively frozen payload
stored in the `RuntimeEnvelope` and delivered to projections. The convenience
`publish(...)` path must not validate the caller's mutable mapping and then
validate the envelope again. `publish_envelope(...)` validates the supplied
envelope once before entering the same already-validated delivery path.

`runtime_event_log_sink(...)` is an optional projection. Its audit projection
preserves the original envelope ID; attaching it never changes event delivery
into log-driven control flow.

Events that can trigger durable or destructive state changes require a
request/job path with idempotency and explicit user approval. Replaying an
audit log must never repeat the action.

Daemon task lifecycle is the first production event boundary. `DaemonState`
injects its one `EventPublisher` into `DaemonScheduler`. Each handler publishes
`daemon/task.started` and exactly one of `task.completed` or `task.failed` under
the installed task context. Event delivery is observational and cannot skip a
handler, change completion, retain a resource, or terminate recurrence. Public
stop/restart uses one 30-second scheduler shutdown budget before authority
ownership is released.

Chat-turn lifecycle is the second production event boundary.
`ConversationGraphRuntime`
requires an instance-scoped publisher and never constructs observability
infrastructure. Application composition creates a private publisher with an
audit subscriber for a standalone surface; `DaemonState` injects its existing
publisher for daemon execution.

- A new logical turn publishes `chat/turn.started` immediately before pipeline
  execution.
- `chat/turn.completed` is published only after `ConversationStore.update()` has
  atomically saved the assistant result. Optional chat-turn trace projection
  also occurs after that commit and outside the per-thread lock. Its payload
  includes duration and stage-trace metadata.
- A completed `turn_id` publishes `chat/turn.reused` after the locked update
  returns, without publishing started or rerunning pipeline/tool work.
- Any exception escaping load, pipeline execution, validation, or persistence
  publishes `chat/turn.failed` with the compact exception chain, then re-raises
  the original exception unchanged. A failure never publishes completed.
- All lifecycle envelopes run under one
  `source="chat_runtime"` context containing the thread and optional turn ID.
  Their audit and daemon live-activity projections retain the envelope ID and
  correlation.
- Event publication is secondary. Projection failure cannot prevent pipeline
  execution, replace a completed response, mask the original failure, or alter
  thread persistence.

`publish_observed_event(...)` is the shared best-effort event-publication
boundary used by worker and chat lifecycle owners. It delegates delivery to
`EventPublisher`, reports delivery failure through structured observability,
and returns the immutable published envelope even when one or more projections
fail. Delivery failure always uses `internal_event_delivery_failed` with exact
`event` and `producer` metadata derived from that envelope; callers cannot
invent subsystem-specific failure projections.

Event projections use the same complete identity as the sealed definition
registry. A projection either receives every registered event or supplies both
`producer` and `name`; supplying only one field is invalid. Exact selectors are
resolved during attachment, so unknown identities fail at composition time.
Name-only and producer-only wildcard projections are not supported. Events
with the same name but another producer never reach an exact projection.

Daemon request dispatch owns a separate sealed audit registry for
`request_rejected`, `chat_turn_failed`, `chat_turn_completed`, and
`shutdown_requested`. The registry fixes presentation and validates exact
metadata before observability. Request handlers never write these records
directly.

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

Each activity batch carries exact `events` and `dropped_count` fields. The
count is a non-negative integer recording events evicted from that subscription
since its previous read; booleans are invalid. A positive count is a stream
gap, not a healthy partial batch. The client must not present that batch and
must switch to the persisted turn-scoped cursor so the authoritative log can
recover both evicted and retained records without duplicating identities
already delivered by earlier healthy batches.

Activity delivery is auxiliary to the chat result. Open, poll, final-drain, and
close failures emit `chat/activity_transport_degraded` through shared
observability with `stage`, subscription id when allocated, and structured
daemon-client failure fields when available. Open, poll, and final-drain
failure switch to the existing turn-scoped incremental cursor so persisted
events remain recoverable. Subscription-delivered event identities are marked
seen on that cursor before presentation, so fallback does not replay them.
Healthy daemon-attached activity never polls files. Close failure is diagnostic
only. Failure of the degradation diagnostic cannot fail, retry, or replace the
chat result.

Live lifecycle visibility follows the registered dotted runtime event names
(`turn.started`, `turn.completed`, `turn.reused`, and `turn.failed`) plus current
audit definitions. The presenter does not carry aliases for removed historical
event spellings.

The request-scoped audit projection is attached through
`project_log_events(...)`. It is an additive, bounded process-local effect
rather than part of `RuntimeContext`. Nested projections compose, active
projection identities are skipped during reentrant log writes, and projection
failure is isolated after the audit record is written. Projections are not
blanket-propagated into new threads or long-lived workers.

## Durable Jobs

Retryable domain work keeps its authoritative state in repositories, outboxes,
or manifests. `RuntimeEnvelope(kind="job")` and `JobMessage` remain the strict
wake-up contract: stable job identity lives in context, while resource identity
and validated hints live in `JobPayload`. Producers receive a `JobSink` through
composition and never install process-global callbacks.

`JobDefinitionRegistry` owns allowed names, producers, and exact domain payload
validation. Local producers create through the registry; decoded external
messages are validated again before scheduler admission.

Reason-export wake-ups use `DaemonScheduler` identity and resource admission.
Initial and reconciliation messages coalesce. Retry identities include their
durable attempt number so an active failed attempt can schedule its successor
without overlap. Delays use scheduler `run_at`, not a separate Timer owner.
Queue pressure never invalidates a durable manifest; startup reconciliation
rediscovers every non-terminal export after a crash.

## Logging

Structured logs are an append-only sink and read model.

- `LogEvent` will become a projection of the shared runtime envelope.
- Every newly written event has a stable id and schema version.
- Ephemeral runtime events and their producer ownership come from registered
  definitions. Their audit projections retain that registered dotted name.
- Direct domain audit writes use stable validated slugs governed by the
  owning domain spec rather than a process-global definition registry.
- Domains with a closed audit taxonomy use a sealed domain-local registry
  built on the shared definition-registry mechanics. Each definition owns its
  component and payload validator. Producers resolve and validate before the
  best-effort sink: an unknown event or invalid level, status, error, or
  metadata is a programming error, not an audit persistence failure.
- Neutral audit component and level types live below the log sink in
  `runtime.audit.types`; definition infrastructure must not import the
  persistence module merely to describe a contract.
- The immutable log projection and record codec live below persistence in
  `nuself.log.record`. Protocol, audit-definition, and presentation modules
  import that model directly. `nuself.log.store` owns filesystem persistence
  and `nuself.log.reader` owns reads and cursors; neither is a facade for the
  neutral record type.
- Metadata must be JSON-safe before it reaches the sink.
- Runtime envelopes and log events use the same recursive JSON freeze/thaw
  boundary. Frozen payloads do not retain caller container aliases, while
  serialized records are detached mutable dict/list trees.
- Boundary adapters must not re-normalize a validated record by coercing keys
  or arbitrary values. Daemon activity encoding consumes the detached
  `LogEvent.to_record()` result directly and leaves final wire validation to
  the daemon protocol codec.
- File writes are serialized per project/component.
- A component file's process-local write mutex is non-reentrant. Observer
  projections and fallback diagnostics run only after the append critical
  section, so recursive log writes never require reacquiring that mutex.
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

It owns two closed infrastructure diagnostics:

| Event | Message | Level/status | Exact metadata |
|---|---|---|---|
| `observability_projection_failed` | `Secondary observability projection failed` | warning/degraded, required error | `failed_event` |
| `internal_event_delivery_failed` | `Internal event delivery failed` | warning/degraded, required error | `event`, `producer` |

Definitions exist for every declared log component and are sealed before
runtime use. The caught exception is represented once by the canonical
top-level error chain. Primary schema errors occur before these boundaries and
must not be relabeled as infrastructure failures.

Auxiliary structured logs must call `write_observed_log_event(...)` directly.
They must not recreate that typed projection by passing a
`write_log_event(...)` closure to `run_observed_best_effort(...)`.
`run_observed_best_effort(...)` remains the generic boundary for secondary
effects that are not themselves structured-log writes.

`write_observed_log_event(...)` constructs exactly one immutable audit envelope
before entering its persistence-failure boundary. Producer identity, payload,
and JSON schema errors therefore propagate as caller contract failures. The
same envelope instance, including its frozen metadata, captured context,
message ID, and creation time, is then passed to `write_audit_envelope(...)`.
Only persistence of that already-validated envelope is degraded into
`observability_projection_failed`; the original envelope is never reconstructed
or retried.

`nuself.runtime.diagnostics.emit_runtime_warning` is the terminal warning
primitive for that fallback and other non-authoritative observers. It catches
warning filters or hooks that promote or fail `RuntimeWarning`, so
process-global warning policy cannot replace the primary result or exception.
It does not retry or recursively report its own failure.

`runtime/warning_definitions.py` owns duplicate-safe, sealed terminal-warning
definitions. A definition fixes one slash-qualified warning identity, exact
ordered fields, domain validation, and an optional fixed suffix. Rendering is
canonical and credential-safe. Domain owners compose closed registries and
pass typed facts; they do not interpolate warning strings at call sites.

Agent tool middleware composes two closed warning definitions for an
unreported tool-log callback failure and for a failure reporter that itself
fails. These are terminal observation diagnostics, not tool execution events;
they contain only safe callback/reporter error facts.

Daemon lifecycle composes the single raw process-log rotation warning
definition. This terminal retention-maintenance diagnostic remains distinct
from structured component-log rotation and never attempts a structured write.

Shared observability owns a sealed one-event terminal-warning registry:

| Warning | Exact ordered fields |
|---|---|
| `runtime/observability_sink_failed` | `component`, `event`, `observed_error`, `log_error` |

The warning identity describes the infrastructure failure. The component and
business audit event are facts, not a dynamically constructed warning
identity. The observed failure retains its canonical compact exception chain.
The sink failure uses its own fail-safe diagnostic message rather than
inheriting the active observed exception as context and duplicating it across
both fields. Sink failure never retries the audit or recursively writes another
structured diagnostic.

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

## Owned One-Shot Execution

`nuself.runtime.execution.OwnedCall` owns one result-producing thread whose
callable runs exactly once. Unlike daemon tasks, a call transports one value or
one escaping `BaseException` directly back to its initiating thread.

- Construction rejects a non-callable target.
- Construction captures one complete copied Python context; the target runs
  inside it regardless of the context active when `start()` is later called.
- `start()` is duplicate-safe. Thread-start failure atomically restores the
  unstarted state and propagates the original failure.
- The target stores either its return value or the same escaping exception
  object and traceback, then signals completion exactly once.
- `wait(timeout)` reports completion without consuming the outcome. Timeouts
  must be finite and non-negative; omitting the timeout waits until completion.
- `outcome(timeout)` returns one typed value/error record after completion and
  raises `TimeoutError` while the call is still running.
- The owned thread is not a daemon thread. Process exit must not silently
  truncate an in-flight authoritative operation.
- `OwnedCall` does not invent cancellation. A caller that requires prompt
  cancellation must provide a domain operation with an explicit cooperative
  cancellation contract rather than abandoning or attempting to kill a Python
  thread.

The CLI live-activity boundary uses `OwnedCall` for its blocking send. Every
exit after a successful start waits for completion before returning or
re-raising, including unexpected poll/presentation failure and process-control
exceptions. Activity processing stops immediately after such a primary
failure, and subscription cleanup still runs. The call outcome cannot replace
that primary failure.

## Daemon Instance Ownership

Each authority has at most one daemon owner. Before reading, deleting,
creating, or binding daemon socket/PID resources, `run_daemon()` must acquire a
non-blocking exclusive process lock at
`<authority-root>/runtime/nuself.lock`. The lock file is a stable coordination
inode and is not deleted during normal cleanup. The socket uses the short
owner-private runtime base selected by `RuntimePaths` and is named from the
authority ID; PID and lock metadata remain under the authority root.

Failed lock acquisition closes its newly opened file handle before returning
contention or another flock error. Release marks the Python owner inactive,
attempts unlock, and always attempts handle close. A single failure retains its
existing exception contract. If flock/unlock and close both fail,
`DaemonInstanceLockCleanupError` retains `operation`, `primary_error`, and
`cleanup_error`, with the primary lock operation as its explicit cause.
Handle cleanup never silently masks the lock ownership failure, and no lock or
close operation is retried.

The owner holds the lock until request serving and scheduler
shutdown are complete. Only that owner may:

- reconcile stale authority socket and `nuself.pid` before initialization;
- publish `nuself.pid`;
- remove the socket and PID during cleanup.

Reconciliation attempts removal of both stale resources independently while the
instance lock is held. Any failures are retained together in a typed recovery
error and abort startup; later lifecycle cleanup still attempts both resources.
Successful reconciliation emits one best-effort
`daemon/runtime_metadata_recovered` audit with boolean socket/PID fields and no
file contents.

While holding that ownership, the daemon temporarily owns the process SIGINT
and SIGTERM handlers through `DaemonSignalOwner`. It restores pre-existing
handlers before project storage/socket/PID cleanup completes and before the
instance lock is released. Handler installation and restoration are explicit
lifecycle operations, not permanent module-level side effects.

If the lock is already held, the contender writes
`daemon/instance_lock_contended`, returns a non-zero exit status, and must not
construct daemon state or modify socket/PID resources. Unix-server binding must
complete before PID publication and before the scheduler starts. The PID
record therefore never claims a daemon whose socket failed to bind. Any
reconciliation, bind, PID-publication, or partial-start failure still runs every
owner cleanup step before the lock is released. Cleanup failures are named and
aggregated without discarding the primary failure. The daemon resets only the
current project root's default storage backend; other in-process project
backends are not part of its ownership.

Daemon readiness has one ordered publication boundary:

1. bind the Unix socket;
2. publish the current PID;
3. start the unified scheduler and admit recurring tasks;
4. require the scheduler dispatcher to remain running;
5. project `daemon/started` and mark the lifecycle ready;
6. begin accepting socket requests.

The `started` projection is best-effort and cannot prevent readiness. A scheduler
startup or readiness failure before step 5 is a startup failure: it runs
full cleanup but must not publish `started` or the matching successful
`stopped` lifecycle record. A daemon ping can succeed only after this boundary
because request handling begins last.

Client lifecycle observation uses one explicit phase model:

| Phase | Typed ping | Instance lock | Meaning |
| --- | --- | --- | --- |
| `stopped` | no | free | no daemon owns or serves the project |
| `owned_unready` | no | held | startup, cleanup, or an unresponsive owner |
| `ready` | yes | held | authoritative service readiness |
| `inconsistent` | yes | free | protocol responder violates ownership |
| `unknown` | known or unknown | inspection failed | partial snapshot attached to a typed status error |

`DaemonStatus.running` is derived solely from `phase == "ready"`; it is not
stored independently. Instance ownership is likewise derived from the phase;
lifecycle errors retain the authoritative status snapshot rather than storing
a second ownership value that could disagree with it. Only `ready` may carry a
PID; construction rejects PID
identity on every other phase. PID metadata is read only for `ready`. Lock
inspection failure must never collapse to `stopped`: the lifecycle raises a
typed status error retaining an `unknown` partial snapshot and the original
cause. If the stable lock file has never existed, observation returns `stopped`
without creating runtime directories or metadata.

A status value is an immutable point-in-time observation, not a lease. Callers
must not cache it across commands or use elapsed-time expiry as a substitute
for a fresh lifecycle decision. A synchronous operation may explicitly reuse
the snapshot that triggered that same operation, avoiding a duplicate typed
ping and lock probe. Lifecycle code validates that a supplied snapshot names
the requested runtime socket and PID paths before using it. Any later polling
iteration always observes a fresh snapshot; the instance lock remains the
authoritative race boundary for competing process startup.

Successful lifecycle mutations return typed transition results rather than a
bare final status. A start result retains `before`, final `status`, and outcome
`started` or `already_ready`; a stop result retains the same snapshots with
outcome `stopped` or `already_stopped`. Their `changed` flag is derived from the
outcome. Result construction rejects before/final snapshots from different
runtime paths and final phases inconsistent with the operation. A restart
result contains both transition results and requires the start input to equal
the stop output, so callers never infer whether work occurred from the final
phase alone.

Restart is one lifecycle orchestration owned by the shared CLI lifecycle
boundary, not separate one-shot and REPL algorithms. It stops first, then uses
the stop result's final status as the explicit initial snapshot for start.
Therefore it does not repeat a fresh initial status probe between its two
ordered phases; later start polling remains fresh.

### PID Metadata

After socket binding, the lock owner publishes
`<authority-root>/runtime/nuself.pid` through atomic text-file replacement. A
valid PID record is one positive base-10 integer; surrounding whitespace is
ignored.

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
