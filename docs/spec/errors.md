# Error Handling Spec

NuSelf should fail in a way that preserves root-cause information, avoids repeated harmful work, and keeps the user in control.

## Principles

1. **Preserve causality**: Wrapping errors is allowed only if the original cause remains available in logs and daemon responses.
2. **Retry only transport failures**: Automatic retry is for connection, timeout, or transient transport failures. Runtime, graph, validation, protocol, and application errors must not be retried automatically.
3. **Keep the REPL alive**: Interactive failures should return to the prompt unless the process itself cannot continue.
4. **Separate user view from audit trail**: User-facing errors are concise. Logs retain structured details needed for debugging.
5. **Do not hide partial progress**: Logs produced before a failure must still be captured, printed, and exported.

Diagnostic detail must not persist credentials. Shared diagnostic sanitization
replaces credential-like labeled values, bearer credentials, and recognized
raw provider keys with `***` while retaining surrounding failure context.
Domain boundaries apply sanitization before truncation or persistence.
Single-exception projections use the shared safe diagnostic-message formatter
rather than calling `str(exception)` locally. The formatter cannot raise when
exception rendering fails and sanitizes before returning text.
CLI adapters use this formatter for every caught exception they render or
project. Local command modules must not interpolate caught exceptions directly.
The same rule applies to agent tools, domain fallbacks, exception wrappers,
daemon payload adapters, background status, and configuration warnings.
Control-flow classification may inspect `safe_exception_message(...)`, but it
must not use a formatting failure as a new application failure.

## Error Classes

| Class | Examples | Retry | User behavior |
|---|---|---|---|
| Transport | daemon socket timeout, connection refused, broken pipe | Yes, once in REPL chat | Print the transport error, preserve logs, retry the same user message once |
| Application | conversation graph node failure, LLM protocol parse failure, memory validation error | No | Print concise error and return to prompt |
| User input | missing command arg, invalid ID, unsupported command | No | Print command-specific error/help; do not run side effects |
| Background | curator, reflection, notification loop failure | No immediate chat retry | Log error and keep the owning loop/process alive when possible |
| Fatal process | daemon cannot bind socket, corrupted runtime path permissions | No | Exit current command with non-zero status |

## User-Facing Failure Disposition

Exception inheritance does not decide terminal behavior. CLI boundaries map
known conditions to one typed disposition with orthogonal kind, retry policy,
session policy, action, and exit status.

Kinds are `setup_required`, `invalid_input`, `temporary_unavailable`,
`operation_failed`, `corrupt_state`, and `internal_error`. Retry policy is
`never`, `user`, `automatic_once`, or `scheduled`. Session policy is
`exit_before_start`, `end_session`, `return_to_prompt`, or
`continue_degraded`.

Stable CLI exit statuses are:

| Status | Meaning |
|---|---|
| `0` | success |
| `1` | ordinary operation failure or internal error |
| `2` | command syntax or user input error |
| `3` | initialization/configuration prerequisite missing |
| `4` | temporary unavailability; a later retry is appropriate |
| `5` | corrupt or unsafe authority state |
| `130` | one-shot command interrupted by the user |

NuSelf represents this table internally with the `CliExitCode` `IntEnum`.
Command, readiness, and interactive transport infrastructure use named enum
members rather than numeric literals. Conversion to a plain integer is only a
process-boundary concern; the numeric interface above remains stable for
shells and other callers.

Terminal EOF and `KeyboardInterrupt` are user control, not application
failures. EOF at the main REPL prompt is a successful session exit. Ctrl-C at
an idle prompt cancels only the current line; Ctrl-C during a turn cancels the
client wait and returns to the prompt after owned transport cleanup. A Ctrl-C
escaping a one-shot command still runs the outer storage cleanup and returns
status `130` without a traceback. If that cleanup fails, the cleanup aggregate
retains the interrupt as its primary cause and takes precedence.

EOF or Ctrl-C at a destructive confirmation is a negative decision and must
not mutate state. Interactive approval prompts record the negative decision;
one-shot CLI confirmation returns the typed interrupted status. Watch commands
that explicitly advertise Ctrl-C as their stop control treat it as a
successful, fully unwound stop.

One-shot commands always terminate after rendering their disposition.
Interactive transport failures keep the REPL alive. A retryable result states
whether the request may already have completed and retains the original
logical turn identity for an explicit safe retry. Missing initialization,
invalid configuration, and missing required model capability are startup
preconditions: an entrypoint must report the concrete action and exit before
starting a daemon or entering the REPL.

Disposition messages are safe projections, not raw exception strings. They may
include a selected managed path and a literal recovery command, but never
credentials, record payloads, or daemon process-log content.

## Exception Chain Contract

- Internal code may wrap exceptions with subsystem context, for example `conversation graph node 'initial_response' failed while handling thread 'default'`.
- The root cause must remain attached via Python exception chaining (`raise ... from exc`).
- Daemon boundaries must serialize a compact exception chain into the returned error and the structured log `error` field.
- Compact chain format:

  ```text
  outer context <- root cause
  ```

- The chain should include unique, non-empty messages only. It should not include full tracebacks in normal user-facing output.
- Compact-chain formatting is itself a diagnostic projection and therefore
  sanitizes credential-like values before returning. Callers must not need to
  remember a second redaction step.
- Formatting an exception is itself a secondary diagnostic operation. If
  `str(exception)` fails, compact formatting must use the exception class name
  and retain the original exception object and chain. A broken exception
  renderer must never replace the failure being reported.
- Full tracebacks may be added later behind an explicit debug/development mode, but they must not be required to understand the likely root cause.

## Daemon Chat Failures

When daemon chat handling fails:

- The chat runtime publishes `chat/turn.failed` when load, graph execution,
  validation, or persistence fails.
- The daemon request layer writes `daemon/chat_turn_failed` with:
  - `level=error`
  - `status=error`
  - `conversation_id`
  - `reason_id`
  - `request_id`
  - `turn_id` when the request supplied one
  - compact exception chain in `error`
- Return a failed daemon response whose `error` field is the same compact exception chain.
- Do not save a partial assistant message for a failed turn.
- Preserve pre-failure log events, including persona, reflection, memory, and chat logs.
- `chat_turn_failed` is an auxiliary projection of that response decision. Its
  failure or diagnostic failure cannot replace the original compact exception
  chain returned to the client.
- `chat_turn_completed` is auxiliary after a valid result/payload exists; its
  failure cannot turn the completed turn into an error response.
- An accepted shutdown request sets the shutdown flag authoritatively.
  `shutdown_requested` audit failure cannot prevent the flag or success
  response.

The daemon request layer owns one sealed audit contract:

| Event | Level | Status | Error / duration | Exact metadata |
|---|---|---|---|---|
| `request_rejected` | warning | `error` | required error, no duration | `request_type` |
| `chat_turn_failed` | error | `error` | required error, no duration | none |
| `chat_turn_completed` | info | `ok` | no error, required duration | non-negative `evidence_references` |
| `shutdown_requested` | info | `accepted` | no error or duration | none |

Messages are fixed by the request audit adapter. Producers supply only event
schema data and correlation; they cannot choose messages, levels, statuses, or
error policy. Unknown events, missing or extra metadata, invalid counts,
invalid counts and duration/error combinations fail before the
best-effort sink.

Request events are distinct from Chat runtime events: Chat `turn.*` describes
agent execution, while daemon request audits describe the response or shutdown
decision at the request boundary.

## Daemon Transport Failures

Clean EOF before a request frame is a normal abandoned connection and produces
no response. Incomplete, oversized, timed-out, or malformed request frames are
rejected before handler dispatch. The server may return a failed response when
the connection remains writable; failure to deliver that response is reported
as a secondary transport diagnostic and never escapes the connection thread.

A typed handler response is a decided business result, but it must pass the
protocol encoder before any bytes are written. Encoding failure is observed as
`daemon/response_encode_failed`; the server then encodes one stable bounded
error response with the same request id. Failure of the encoding diagnostic
does not prevent that fallback. Once a frame write begins, the server never
retries or substitutes another frame because the peer may have received a
prefix. Any write or flush failure, including delivery of the fallback frame,
is observed separately as `daemon/response_delivery_failed`. Encoding
diagnostics retain the decided response status; delivery diagnostics retain
the frame status and whether the frame was an encoding fallback.

The socket transport owns one sealed failure-audit contract:

| Event | Level | Status | Exact metadata |
|---|---|---|---|
| `request_transport_failed` | warning | `error` | none |
| `request_failed` | error | `error` | none |
| `response_encode_failed` | warning | `error` | `response_status=ok|error` |
| `response_delivery_failed` | warning | `error` | `response_status=ok|error`, boolean `fallback` |

Every event requires the canonical top-level error and forbids duration.
Messages and projection defaults are fixed by the transport audit adapter.
Missing/extra metadata, invalid response status, non-boolean fallback, unknown
event, forbidden duration, and missing error fail before the terminal
best-effort diagnostic boundary. A request ID is correlated only after one was
decoded; the internal `unknown` sentinel is never persisted as an identity.

Client-side socket failures and invalid response frames share
`DaemonConnectionError`. The original `OSError` or `ProtocolError` is retained
as the explicit cause. A response with another request's id is invalid even if
its status and payload otherwise decode successfully.

`DaemonConnectionError` carries a stable phase, request id when one was
allocated, derived `retryable`, and derived `request_may_have_completed`.
Phases are `connect`, `request_encode`, `send`, `receive`, `response_decode`,
`response_identity`, `payload_decode`, and `unknown`. Connect, send, receive,
response-decode, response-identity, and legacy unknown failures are retryable
for the REPL's idempotent chat turn. Request encoding and typed success-payload
decoding are not retryable. Send and every later phase mean the request may
already have completed; connect and request encoding do not. The exception
message remains concise and the original cause remains chained.

## Daemon Task Boundary

Every daemon task executes through the unified scheduler boundary. An
unexpected `Exception` completes that task as failed, records only its
payload-safe type and task kind as current scheduler degradation, and publishes
`daemon/task.failed` with the existing sanitized diagnostic boundary.
The next successful task clears current scheduler degradation; historical
failure detail belongs in logs rather than the health snapshot.
Recurring tasks are admitted again only after completion, so failures cannot
kill a dedicated subsystem loop or create overlap. Domain retries must persist
their attempt transition before admitting a successor. Reporting remains a
secondary best-effort effect. Scheduler shutdown closes admission, cancels
pending volatile wake-ups, and waits for already-dispatched authoritative work
within the daemon lifecycle deadline.

## Daemon Lifecycle Cleanup

Daemon startup has one lifecycle-owned readiness boundary. After spawning the
child, it polls daemon readiness against a monotonic deadline and also observes
the child process:

- A child that exits before readiness raises a typed daemon-start failure with
  reason `process_exited` and its exit code.
- A child that remains alive but does not become ready before the deadline
  raises the same typed failure with reason `timeout`.
- Failure to spawn the child raises the same typed failure with reason
  `spawn_failed` and preserves the original exception as its explicit cause.
- The failure retains the latest `DaemonStatus`, but terminal output never
  reads or echoes the raw daemon process log. That stream may contain private
  provider or application output.
- Raw process-log rotation failure resolves the sealed
  `daemon/process_log_rotation_failed` terminal warning with only the exception
  type and a fixed startup-continuation suffix. It cannot block spawn or expose
  the exception message, project path, or process-log content.
- The startup timeout and polling interval are positive finite values owned by
  the shared injectable lifecycle wait policy. Polling uses `time.monotonic()`
  and never sleeps beyond the remaining deadline. Each readiness ping also
  receives no more than the remaining budget, so socket I/O cannot silently
  extend it.
- CLI start, default startup, restart, and interactive restart use the
  lifecycle failure's stable safe message through one formatter shared by
  start and stop errors. One-shot commands exit non-zero; interactive restart
  returns to the existing REPL.
- A failed lifecycle operation is projected as a structured lifecycle audit
  with the reason, latest status, exit code when known, and sanitized compact
  exception chain. The terminal still receives only the stable outer message.
  Audit failure remains secondary and cannot replace the startup failure.

Daemon shutdown has one lifecycle-owned ownership boundary:

- The project instance lock is authoritative for whether a daemon still owns
  the runtime. A successful ping is service readiness, not process ownership;
  a PID file is diagnostic metadata only.
- A stop is complete only when the daemon no longer responds and the instance
  lock has been released. This keeps worker cleanup and runtime-file teardown
  inside the daemon's ownership window.
- The CLI never sends a signal to a numeric PID read from runtime metadata.
  PID files may be stale and operating systems may reuse PIDs, so such a signal
  could target an unrelated process.
- Graceful shutdown uses the same injectable lifecycle wait-policy type with
  its own default instance. The shutdown request, readiness probes, sleeps, and
  final ownership check are all bounded by the same monotonic deadline.
- An explicit shutdown rejection raises a typed stop failure immediately.
  A transport failure may mean the request completed, so the lifecycle retains
  it and continues observing ownership until success or timeout.
- Failure to inspect the instance lock and expiry before both readiness and
  ownership have cleared are typed stop failures. They retain the latest status
  and original request or lock error as an explicit cause.
- CLI stop, restart, and interactive restart use one shared observed stop
  adapter for requested, completed, and failed audit projections. One-shot
  failures exit non-zero; interactive failures keep the existing REPL alive.
- `DaemonStatus.pid` is populated only for a daemon that answered the matching
  project ping. A syntactically valid but stale PID file is never rendered as a
  running-process identity.

Daemon startup recovery runs only after acquiring the project instance lock.
It independently removes stale socket and PID metadata before constructing
daemon state. Multiple recovery failures are retained in one typed error; a
failure aborts initialization but does not skip the normal owned cleanup
boundary. Binding precedes PID publication, so bind failure cannot publish a
current-process PID. Recovery audit failure remains secondary.

Daemon readiness is authoritative only after socket binding, PID publication,
every worker start operation succeeds, and the sealed supervisor confirms that
every registered worker is still `running` and alive. A worker that exits
during startup makes readiness fail even when its thread was spawned
successfully. Readiness also fails if the shared shutdown event was requested
at any point before this check; a process already entering shutdown must never
publish itself ready. The server publishes `started` only after that check and
begins request handling afterward. A partial worker-start, startup-health, or
pre-readiness shutdown failure performs full cleanup without publishing either
a successful `started` or `stopped` record. Failure of the `started` audit
itself remains secondary and does not undo readiness.

Daemon status observation combines typed ping readiness and instance-lock
ownership into the phase model in `runtime-infrastructure.md`. Failure to
inspect ownership raises a typed status error with an `unknown` partial
snapshot and explicit cause. Start wraps it as `status_failed`; stop wraps it
as `ownership_check_failed`. CLI status/list, system checks, launch entrypoints,
interactive headers, and REPL status commands use one shared safe
status-unavailable boundary rather than guessing stopped or exposing the cause.

Daemon shutdown owns an ordered set of named cleanup steps. It signals
shutdown, attempts each worker stop independently, resets only the current
project's default storage backend, removes the socket and PID independently,
and releases the instance lock last.

SIGINT and SIGTERM handlers are process-global borrowed state. The daemon
captures and installs both before binding, keeps them while workers stop, then
restores the exact prior handlers in reverse order as a named cleanup step.
Partial installation immediately attempts to restore every signal already
changed. Installation remains a main-thread requirement; Python's failure
outside the main thread is surfaced rather than silently disabling shutdown.

Signal restoration attempts every still-owned signal. Failures retain the
signal number and remain retryable; a later lifecycle cleanup step still runs.
The daemon must never leave one successfully restored signal marked as owned.

Every `BaseException` from a cleanup step is retained as a shared
`CleanupFailure(step, error)` while later steps continue. When cleanup fails,
`DaemonLifecycleError` exposes the complete ordered failure tuple. If bind,
serve, or another primary operation also failed, that original exception is
retained as `primary_error` and as the lifecycle error's explicit cause. A
cleanup error, including `KeyboardInterrupt` or `SystemExit`, must never
silently replace or discard the primary failure.

Instance-lock acquire/release has the same provenance rule before lifecycle
aggregation. `DaemonInstanceLockCleanupError` is raised only when flock or
unlock fails and closing that operation's file handle also fails. It names the
operation and retains both errors with the lock-operation error as cause.
Ordinary contention, single flock/unlock failure, and single close failure
keep their existing exception behavior.

The `daemon/stopped` audit event is written only after all owned cleanup steps
before instance-lock release succeed. Failed cleanup emits
`daemon/shutdown_cleanup_failed` as a best-effort diagnostic and propagates the
lifecycle error. Failure of that diagnostic does not alter the retained error
set.

Daemon process cleanup failures use one sealed operations audit contract:

| Event | Level | Status | Exact metadata |
|---|---|---|---|
| `shutdown_cleanup_failed` | error | `error` | non-empty ordered `failures` records containing non-empty `step` and canonical `error`, boolean `primary_failed` |

The event requires a canonical top-level error and forbids duration. Cleanup
metadata preserves each retained failure because the aggregate lifecycle
exception intentionally summarizes only the count. The adapter sanitizes each
failure chain through the shared diagnostic path; callers do not format nested
errors, messages, levels, or statuses.

Storage teardown uses one sealed storage operations audit contract:

| Event | Level | Status | Exact metadata |
|---|---|---|---|
| `backend_close_failed` | warning | `degraded` | non-empty `backend_type` |
| `cli_cleanup_failed` | error | `error` | non-empty ordered `failures` records containing non-empty `step` and canonical `error`, boolean `primary_failed` |

Both events require a canonical top-level error and forbid duration. A runtime
records its backend close failure against the authority root and re-raises that
same failure into outer cleanup aggregation. CLI cleanup preserves every
retained step/error chain before raising `CliLifecycleError`.

Daemon lifecycle operations and their typed transition results are
authoritative. The server's contention/started/stopped records and the one-shot
or interactive CLI's requested/completed records are auxiliary projections
through one daemon-owned observable boundary. Audit failure cannot
replace a contention exit, abort a daemon after ownership and initialization
succeed, skip a requested start/stop/restart operation, change its exit code or
rendered status, or replace an interactive restart result.

Successful client lifecycle operations expose typed start/stop transition
results containing the before/final status and an explicit changed-versus-no-op
outcome. Shared restart orchestration retains both results. Completion audits
are projected from those results rather than inferring mutation from the final
status; restart failure metadata additionally names the failed `stop` or
`start` stage.

Lifecycle audit schema violations are producer programming errors, not sink
failures. Unknown events, invalid projection combinations, and malformed
metadata raise before the best-effort persistence boundary; they are never
reported as `observability_projection_failed`. Once a record passes schema
validation, persistence failure remains secondary and cannot replace the
authoritative lifecycle result.

## Best-Effort Side Effects

Some secondary effects must not change the result of an already-successful
primary operation. Examples include audit logging and thought-trace recording
after a memory or persona update.

- These effects run through one shared observable best-effort boundary rather
  than local `try/except/pass` blocks.
- Auxiliary structured logs use
  `write_observed_log_event(component, event, message, ...)`, which mirrors the
  typed log fields and returns the written `LogEvent` or `None`. It never
  retries the original record. On sink failure it records the shared
  `observability_projection_failed` event with exact `failed_event` metadata
  through the same non-recursive reporting boundary.
- Callers supply the intended log event only. They cannot choose the secondary
  failure identity, message, level, status, or metadata.
- A secondary failure does not fail or roll back the primary operation.
- The boundary writes a structured warning with the compact exception chain
  and JSON-safe context.
- The shared observed-failure boundary sanitizes the complete compact chain
  before structured persistence and sanitizes the complete fallback warning
  again if structured logging fails. This includes implicit exception context
  inherited from the operation being diagnosed.
- Audit metadata is recursively copied and sanitized at the canonical log
  projection before persistence. Values under credential-like keys become
  `***`; other string values use shared sensitive-text redaction; nested
  mappings and sequences follow the same rules.
- Sanitization never mutates caller-owned containers and never stringifies or
  coerces unsupported objects. Strict JSON validation remains authoritative;
  invalid diagnostic metadata still reaches the non-raising terminal-warning
  fallback.
- If the structured log sink itself fails, the boundary emits one warning
  through Python's standard warning channel. It must not recursively attempt
  structured logging.

- Best-effort handling is not allowed for authoritative persistence,
  validation, approval, external delivery state, or retryable job transitions.
- Expected parsing fallbacks and cleanup races should use their specific
  exception types and do not need best-effort failure events.

Approval prompt rendering, output, and input are authoritative interaction
effects. Rendering, stdout, and unexpected input failures propagate unchanged;
they must not be converted into a decline. Only `EOFError` means no affirmative
decision can be read and follows the safe-default decline path.

Observed runtime-event publication catches only `EventDeliveryError`.
Definition lookup and envelope/payload validation failures are producer
contract errors and propagate unchanged. A delivery error retains the created
envelope, so the best-effort wrapper returns that envelope after reporting the
failed subscribers rather than claiming that publication never occurred.

Structured log readers isolate corrupt JSON records and report one aggregated
terminal warning per file-read batch. This diagnostic uses the non-raising
runtime warning boundary directly, never the structured log sink, so it cannot
recurse or replace healthy/legacy read results. Raw lines and arbitrary values
are excluded from the warning.

Structured log append lifecycle failures preserve phase provenance.
`LogAppendLifecycleError` is raised when rollback or active data-handle close
fails. It retains the primary append error, rollback error, close error, and
an explicit `persistence_outcome`: `not_persisted`, `persisted`, or
`uncertain`. The primary append error is the explicit cause when present;
otherwise the close error is. A lone append or file-sync error whose durable
rollback and close both succeed remains the original exception. Observer
delivery occurs only after append sync and close both succeed.
Auxiliary chat audits never retry the uncertain record. They report the append
failure through the shared best-effort boundary, while the existing typed
daemon transport result remains the sole retry decision.

Reflection trace recording and organizer execution after a persisted
reflection are secondary under this contract. Corrupt reflection schedule
diagnostics are also secondary to the authoritative fail-closed block/cooldown
decision. Their logging failure cannot turn those outcomes into exceptions.

An accepted LLM response and configured retry, endpoint failover, and local
fallback decisions are authoritative. The last-successful endpoint preference,
retry/failover/fallback/finalize audit records, and chat thought-trace
projection are secondary. Failure of those projections or their diagnostics
cannot discard a valid response, skip the next configured attempt, prevent
local fallback, or replace a completed chat answer with an exception.

The shared agent endpoint audit adapter receives a failure only after the
runner has classified it and decided whether another endpoint exists. It
redacts provider diagnostics before validation and persistence. The adapter
cannot alter availability classification, attempt counts, endpoint order,
raised exception identity, aggregate capability failure, or domain-specific
retry behavior. Failure to persist the audit remains secondary and uses the
shared terminal-warning boundary.

Dynamic REPL completion reads are secondary UI effects. Chat thread completion
failures use the sealed Chat adapter, and Reason thread completion failures use
the sealed Reason adapter. Either adapter may degrade to an empty suggestion
set, but a caller must not select an unregistered message, status, metadata
shape, or generic observability projection.

Process-local log observer failure is a recursive-sensitive logging-core
boundary, not a daemon lifecycle failure or generic secondary projection. Its
sealed log infrastructure definition is validated while observation is
suspended, then persisted directly. If validation or persistence fails, the
single credential-safe runtime warning remains the terminal diagnostic and
cannot alter the original audit write, later observer delivery, or business
operation.

All logging-core terminal warnings resolve through the sealed typed warning
registry before reaching Python warning policy. They are deliberately
non-persisting and non-retrying. Rendering validates the exact field schema,
uses fail-safe exception diagnostics, and redacts the complete warning.
Emission still catches warning-hook and warning-as-error failures, so neither a
schema/render problem nor warning policy may replace the primary log outcome.

Import-time dependency warnings remain owned by Python's standard warning
policy. NuSelf must not replace `warnings.warn`; a documented dependency
warning may use a temporary exact filter around only the import that triggers
it, while unrelated warnings remain visible.

The shared observed-failure sink fallback resolves the sealed
`runtime/observability_sink_failed` warning. It records exactly the failed
audit component/event, the safe observed exception chain, and the safe sink
error message. The sink field excludes the active observed exception context
so the primary diagnostic is not duplicated. It does not retry the structured
write, construct a dynamic warning identity, or allow warning rendering or
emission to replace the caller's result, fallback, or primary exception.

Tool-log callback and callback-failure reporter errors are secondary to the
tool outcome. Agent middleware resolves one of two sealed terminal warnings
when structured reporting is absent or fails. Registered rendering and warning
policy cannot replace a successful `ToolMessage`/`Command`, replace the
original tool exception, append a partial capture, or trigger a tool retry.

Chat's local response policy is not an exception sink for implementation
defects. Before any tool executes, the shared policy rejects assertion,
attribute, import, lookup, memory exhaustion, name resolution, unimplemented
path, recursion, syntax, interpreter-system, and type errors. These errors
propagate unchanged and are ineligible for retry, endpoint failover, or local
fallback. After a tool outcome exists, the non-replay contract suppresses every
further model call only when at least one outcome came from a write-capable
tool. A transient availability failure receives one delayed retry on the same
endpoint before ordered failover. Readonly tool outcomes may be replayed by
that retry because they cannot duplicate mutation. Recoverable failures may
use local fallback; sharedly classified implementation and process-integrity
failures propagate unchanged after retry suppression.

Chat fallback text must identify its actual cause. When no configured endpoint
has a usable API key, it may provide local configuration guidance. When one or
more configured endpoints were invoked but exhausted by a recoverable model,
protocol, or output failure, the fallback must instead state that the
configured LLM request failed and direct the user to diagnostics. It must
remain non-empty, must not claim the API is unconfigured, and must not expose
provider response text, credentials, prompts, or endpoint URLs.

Chat response synthesis prefers the exact typed LangChain
`structured_response`. When an OpenAI-compatible agent successfully returns no
structured response but does return a final, non-empty, text-only framework
`AIMessage`, Chat accepts that message as the answer with no evidence
references, no confidence, and `epistemic_status="inferred"`. It does not parse
JSON from message text, accept a message with unresolved tool calls, or apply
this compatibility path to strict structured decision agents owned by memory,
persona, reflection, or reasoning.

Agent model unavailability, framework protocol violations, and invalid
generated output have separate shared exception types. Endpoint failover
consults exception types and structured status attributes only; it never
parses the rendered exception message. Protocol and output failures propagate
without trying a different endpoint.

Structured endpoint status failover includes request timeout/rate limiting and
transient server availability statuses `408`, `429`, `500`, `502`, `503`, and
`504`, whether exposed directly on an exception, on its response, or through
its exception cause/context chain. Existing endpoint-specific authentication,
permission, and payment statuses `401`, `402`, and `403` remain eligible
because configured endpoints may own independent credentials or accounts.
Client request/schema statuses such as `400`, `404`, and `422` are not
availability failures. Status values must be exact integers, not booleans, and
message text is never parsed.

The pre-tool classification is shared agent infrastructure, not a chat-only
rule. Persona activation, contribution, and synthesis use the same policy:
provider/runtime and validation failures may produce their specified fallback,
but every sharedly classified implementation or process-integrity failure
propagates unchanged.
Chat's outer competitive-discussion orchestration uses the same policy and
must not convert those implementation errors into a normal answer appendix.

Reason-export manifests, composition, delayed-retry scheduling, and worker
lifecycle decisions are authoritative. Export lifecycle and caught-failure
audit records are secondary: audit failure cannot suppress a retry after its
state is durably persisted, block composition after optional progress
degradation, truncate reconciliation, or undo queue drain/shutdown state. A
delayed scheduler start failure rolls back task ownership, emits the sealed
`export_retry_schedule_failed` degradation, and requests manifest
reconciliation; it cannot leave a phantom retry that reconciliation skips.

ReasonService repository/workspace mutations are authoritative. Thread and
step traces plus lifecycle audits are secondary after a successful mutation;
their failure or diagnostic failure cannot replace a committed start, advance,
status transition, or deletion result. Delete success is not projected before
the authoritative delete finishes.

Memory curator candidate/entry/cursor writes and reflection organizer
repository mutations are authoritative. Curator audits, memory-update traces,
and organizer completion audits are secondary projections; failure of a
projection or its structured diagnostic cannot replace or replay committed
domain results.

Notification adapter `False` outcomes for missing email configuration, SMTP
failure, and osascript failure are authoritative. Their failure diagnostics
are secondary and cannot leave an entry pending by raising before
`record_adapter_result`. Log-only, dry-run, external send, and outbox state
writes remain authoritative effects. Once a terminal adapter result is
persisted, crash recovery may finalize its global projection but cannot invoke
that adapter again.

## Atomic File Failure Provenance

Shared atomic text/JSON persistence propagates an ordinary write or replace
exception unchanged when its sibling temporary file is removed successfully.
If that cleanup also fails, `AtomicWriteCleanupError` retains the original
`primary_error`, the `cleanup_error`, and the residual `temporary_path`; the
primary error is its explicit cause. Because both persistence and cleanup are
authoritative, neither failure is degraded into a warning or retried.

After a final memory-candidate write reports visible-but-durability-unknown,
observation is evidentiary rather than a prerequisite for preserving state.
`MemoryCandidateAmbiguousCommitError` retains the durability error plus any
candidate/target observation errors. Observation failure is represented as an
`unknown` state and cannot fall through to target compensation; compensation
requires a successful read proving the candidate is not accepted.

The same pre-replace rule applies to file-content synchronization and
`BaseException` interruption. After atomic replacement, a parent-directory
sync failure instead raises `AtomicWriteDurabilityError`: the destination
contains the new complete value in the running system, while survival across a
crash remains uncertain. It exposes `destination_path` and `sync_error`, uses
the sync failure as its explicit cause, and never attempts to unlink the
already-consumed temporary pathname.

SQLite transaction rollback dual failure uses the existing
`SqliteTransactionCleanupError`. It exposes both `primary_error` and
`rollback_error` as `BaseException` values and uses `primary_error` as its
explicit cause. This applies uniformly to transaction-body, interruption,
commit, and rollback-only failures; message text is diagnostic, not a schema.
Rollback-only and rollback-cleanup failures are separate direct runtime errors;
there is no transaction-error family without an independent catch policy.
Workspace SQLite batches follow the same provenance rule across operation,
commit, rollback, and connection-close failures. Their lifecycle error retains
the primary failure plus any rollback and close failures, and uses the primary
failure as its explicit cause. A close failure after successful commit has no
primary failure and must not trigger rollback or replay.

## Corrupt Record Isolation

Collection listing and rebuild operations isolate malformed records so one bad
record does not hide healthy neighbors.

- Repositories use one shared decode boundary for stored record dictionaries.
- Only declared schema/decode errors such as `ValueError`, `KeyError`, and
  `TypeError` are isolated. Unexpected programming or infrastructure errors
  propagate normally.
- Each isolated record writes a structured `record_decode_failed` warning with
  the collection name, recoverable record ID or `"<unknown>"`, and compact
  exception chain.
- Diagnostics must not include the complete record, private body, prompt,
  source text, or other arbitrary payload fields.
- Listing does not rewrite, quarantine, or delete the malformed record.
- Direct `get` operations continue to surface decode errors to their caller;
  silently converting corrupt data into "not found" is forbidden.

## REPL Retry Contract

Interactive chat may retry exactly once only when the send result is explicitly marked retryable.

Daemon activity subscription transport is not the chat send result. Its
open/poll/drain/close failures are observed as auxiliary degradation and never
trigger or suppress a chat retry. Open, poll, and drain failure may recover
persisted turn events through the incremental cursor; close failure only
affects subscription cleanup.

Unexpected live-chat callback `Exception` values are observed as
`chat/interactive_send_failed` and become a non-retryable interactive failure;
failure of that diagnostic cannot replace the callback error. Callback
`KeyboardInterrupt`, `SystemExit`, and other non-`Exception` `BaseException`
values remain control flow. The same object is re-raised on the main thread
after subscription close, with cause and traceback retained. Auxiliary final
drain is skipped so it cannot mask the control exception.

Manual interruption is an owned cancellation boundary, not permission to
abandon a request thread. When the main thread receives `KeyboardInterrupt`
during a live send, it first requests cooperative cancellation of that send.
A daemon request reacts by shutting down its owned client socket, then the
main thread waits for the owned call to reach a terminal outcome and closes
the activity subscription before propagating the original control exception.
Cancellation-caused transport failure is subordinate to that original control
exception and must not be presented as a retryable chat failure. Waiting for a
send without first requesting cancellation is forbidden. A later Ctrl-C
received during the bounded reaping window cannot replace the original
control exception or skip owned-call cleanup.

REPL exit cleanup uses one lifecycle aggregation boundary. The ordered steps
are `transcript.auto_save` and `memory.curator.run`. Both execute exactly once
and all caught `BaseException` values are retained as named
shared `CleanupFailure` entries. When cleanup fails,
`InteractiveLifecycleError` retains the tuple and the main-loop
`primary_error`; the primary is its explicit cause when present. If cleanup
succeeds, the original main-loop exception is re-raised with its traceback.
`chat/interactive_cleanup_failed` is an auxiliary diagnostic of the aggregate;
failure of that diagnostic cannot replace the lifecycle error.

The outer CLI lifecycle always attempts `storage.default_backend.reset` after
command dispatch, including when dispatch raises `KeyboardInterrupt`,
`SystemExit`, or another `BaseException`. A reset failure is retained as a
named `CleanupFailure` in `CliLifecycleError`. If dispatch also failed, the
same primary object is retained on the lifecycle error and is its explicit
cause. If reset succeeds, the original dispatch exception is re-raised with
its traceback. Storage teardown runs outside and after REPL-specific cleanup.

## Local REPL Command Failures

A local REPL command may catch an unexpected `Exception` only when the command
owns a recoverable interactive boundary and returns a concise error while
keeping the session usable. Such a catch must also call the shared observable
failure boundary:

- `:persona` uses `persona/interactive_command_failed` and records the command
  action without recording prompt text or other command arguments;
- `:history` uses `chat/interactive_history_load_failed` and records the
  requested thread ID;
- the structured `error` field retains the compact exception chain;
- diagnostic persistence failure falls back to a runtime warning and cannot
  replace the command's existing rendered error;
- `KeyboardInterrupt`, `SystemExit`, and other non-`Exception` control flow are
  not converted into command results.

Commands without an explicitly recoverable boundary continue to propagate
unexpected failures to their owner. A broad catch must not be added merely to
keep the prompt alive.

Reason commands follow the declared reason-domain hierarchy rather than
catching `RuntimeError`. Expected not-found, prompt, advance, and transition
errors remain concise command results; undeclared implementation or
infrastructure `RuntimeError` values are not relabeled as user mistakes.

Retryable:

- daemon connection timeout
- daemon connection failure before a response is received
- send/receive failure where the stable chat `turn_id` makes replay safe
- malformed, incomplete, or mismatched daemon response frames

Not retryable:

- daemon response with `status=error`
- locally unencodable daemon request
- malformed typed payload inside a successfully decoded response envelope
- conversation graph node failure
- LLM output/schema/protocol failure
- memory/profile/source validation failure
- unsupported tool or command semantics

For retryable failures, the REPL must:

1. Print/capture any logs produced before the failure.
2. Print a retry notice.
3. Retry the same logical turn once, reusing the original `turn_id`.
4. If the retry fails, print `Message failed after retry; REPL remains open.`

Retry idempotency:

- The retry must not persist the same user input twice.
- A persisted `turn_id` is permanently bound to its original user input. A
  retry that reuses the ID with different input fails with an explicit turn
  conflict before model or tool execution.
- Before model or tool execution, a stable turn writes an internal pending
  marker containing its ID and input digest into the locked thread state. The
  completed thread write removes that marker in the same transaction that
  saves the assistant reply. A retry that finds a matching unfinished marker
  fails closed instead of replaying a possibly committed tool side effect; a
  mismatched digest is a turn conflict. A process crash or final thread-write
  failure intentionally leaves the marker as recovery evidence.
- If the daemon completed the first attempt after the client timed out, the retry must return the already-persisted assistant reply for that `turn_id`.
- Already-produced logs, including persona activation and persona discussion logs, remain the record of the logical turn. A retry that resolves from an already-completed `turn_id` must not rerun persona work just to recreate those logs.

For non-retryable failures, the REPL must:

1. Print/capture any logs produced before the failure.
2. Print the error through the rendered log when an equivalent error log exists.
3. Print a separate stderr error only when no equivalent rendered error log was captured for the turn.
4. Return to the prompt without retrying.

## Log Rendering

Human-readable error logs follow the shared log style from [`cli.md`](cli.md):

```text
[chat] turn.failed status=error thread=default request=<id> error="outer <- root"
  chat turn failed
```

Daemon request-layer failures render as `[daemon] chat_turn_failed ...` and preserve the same compact exception chain.

The `error` field should stay in the header when short enough for the normal renderer. Longer body text, if introduced later, should be rendered as an indented body rather than raw JSON.

## Transcript Export

Transcript export must preserve failure logs in the same relative turn position as successful logs.

- Shareable logs include high-level failure logs only when they are part of the visible interaction.
- Transcript logs use human-readable rendering, not JSON.
- A failed turn with no assistant reply may still have logs associated with the user message.

## Testing Requirements

Error-handling changes should include tests for:

- root cause survives daemon response boundaries;
- REPL retries transport failures once;
- retry attempts reuse one `turn_id` and do not duplicate persisted user input;
- REPL does not retry daemon/application errors;
- logs produced before failure are still printed/captured;
- transcript export remains valid Markdown when failure logs are included.
- curator, reflection, reason, export, and notification worker boundaries stay
  alive and log an unexpected non-`RuntimeError` iteration failure.
