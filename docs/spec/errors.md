# Error Handling Spec

NuSelf should fail in a way that preserves root-cause information, avoids repeated harmful work, and keeps the user in control.

## Principles

1. **Preserve causality**: Wrapping errors is allowed only if the original cause remains available in logs and daemon responses.
2. **Retry only transport failures**: Automatic retry is for connection, timeout, or transient transport failures. Runtime, graph, validation, protocol, and application errors must not be retried automatically.
3. **Keep the REPL alive**: Interactive failures should return to the prompt unless the process itself cannot continue.
4. **Separate user view from audit trail**: User-facing errors are concise. Logs retain structured details needed for debugging.
5. **Do not hide partial progress**: Logs produced before a failure must still be captured, printed, and exported.

## Error Classes

| Class | Examples | Retry | User behavior |
|---|---|---|---|
| Transport | daemon socket timeout, connection refused, broken pipe | Yes, once in REPL chat | Print the transport error, preserve logs, retry the same user message once |
| Application | conversation graph node failure, LLM protocol parse failure, memory validation error | No | Print concise error and return to prompt |
| User input | missing command arg, invalid ID, unsupported command | No | Print command-specific error/help; do not run side effects |
| Background | curator, reflection, notification loop failure | No immediate chat retry | Log error and keep the owning loop/process alive when possible |
| Fatal process | daemon cannot bind socket, corrupted runtime path permissions | No | Exit current command with non-zero status |

## Exception Chain Contract

- Internal code may wrap exceptions with subsystem context, for example `conversation graph node 'initial_response' failed while handling thread 'default'`.
- The root cause must remain attached via Python exception chaining (`raise ... from exc`).
- Daemon boundaries must serialize a compact exception chain into the returned error and the structured log `error` field.
- Compact chain format:

  ```text
  outer context <- root cause
  ```

- The chain should include unique, non-empty messages only. It should not include full tracebacks in normal user-facing output.
- Full tracebacks may be added later behind an explicit debug/development mode, but they must not be required to understand the likely root cause.

## Daemon Chat Failures

When daemon chat handling fails:

- The chat runtime publishes `chat/turn.failed` when load, graph execution,
  validation, or persistence fails.
- The daemon request layer writes `daemon/chat_turn_failed` with:
  - `level=error`
  - `status=error`
  - `thread_id`
  - `request_id`
  - `turn_id` when the request supplied one
  - compact exception chain in `error`
- Return a failed daemon response whose `error` field is the same compact exception chain.
- Do not save a partial assistant message for a failed turn.
- Preserve pre-failure log events, including persona, reflection, memory, and chat logs.

## Daemon Transport Failures

Clean EOF before a request frame is a normal abandoned connection and produces
no response. Incomplete, oversized, timed-out, or malformed request frames are
rejected before handler dispatch. The server may return a failed response when
the connection remains writable; failure to deliver that response is reported
as a secondary transport diagnostic and never escapes the connection thread.

Client-side socket failures and invalid response frames share
`DaemonConnectionError`. The original `OSError` or `ProtocolError` is retained
as the explicit cause. A response with another request's id is invalid even if
its status and payload otherwise decode successfully.

## Background Worker Boundary

Every daemon-owned background worker must keep its loop alive after an
unexpected per-iteration exception unless shutdown has been requested.

- The outer iteration boundary catches `Exception`, preserves the compact
  exception chain in a structured error log, and continues after the normal
  configured interval.
- Catching only an expected application exception is insufficient at this
  boundary because validation, storage, and adapter failures must not silently
  terminate the worker thread.
- Workers track their last successful run, last error, consecutive failure
  count, and thread liveness so daemon status can expose degraded subsystems.
- All worker targets run inside `source="daemon.worker.<name>"` runtime
  context. A target-level exception that escapes initialization or the loop is
  recorded in health and published as `daemon/worker.failed`
  before the owned thread becomes stopped.
- The structured error write is a secondary reporting effect. If it fails,
  shared observability emits a Python warning; logging failure must not escape
  the iteration boundary or terminate an otherwise recoverable worker.
- The loop itself must not retry the failed operation immediately. The next
  configured scheduled iteration is the retry boundary.
- Dependencies required before a worker loop starts are constructed by its
  synchronous `start_background_*` boundary before thread ownership. Those
  initialization failures remain daemon startup failures and surface to the
  caller.
- A retryable worker operation must persist its retry/attempt transition before
  scheduling another execution. If that durable transition fails, log the
  state-persistence failure separately and do not enqueue an untracked retry.
- Worker join timeouts produce a daemon warning with worker identity and
  timeout. The worker remains reported alive/timed-out until its target exits;
  shutdown must not claim a successful join.

## Daemon Lifecycle Cleanup

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

Every ordinary `Exception` from a cleanup step is retained as a
`DaemonCleanupFailure(step, error)` while later steps continue. When cleanup
fails, `DaemonLifecycleError` exposes the complete ordered failure tuple. If
bind, serve, or another primary operation also failed, that original exception
is retained as `primary_error` and as the lifecycle error's explicit cause.
A cleanup error must never silently replace or discard the primary failure.

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

## Best-Effort Side Effects

Some secondary effects must not change the result of an already-successful
primary operation. Examples include audit logging and thought-trace recording
after a memory or persona update.

- These effects run through one shared observable best-effort boundary rather
  than local `try/except/pass` blocks.
- The caller supplies the owning component, a stable failure event name,
  operation context, and the secondary callable.
- A secondary failure does not fail or roll back the primary operation.
- The boundary writes a structured warning with the compact exception chain
  and JSON-safe context.
- If the structured log sink itself fails, the boundary emits one warning
  through Python's standard warning channel. It must not recursively attempt
  structured logging.
- Best-effort handling is not allowed for authoritative persistence,
  validation, approval, external delivery state, or retryable job transitions.
- Expected parsing fallbacks and cleanup races should use their specific
  exception types and do not need best-effort failure events.

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

Reason-export manifests, composition, retry timer creation/start, and worker
lifecycle decisions are authoritative. Export lifecycle and caught-failure
audit records are secondary: audit failure cannot suppress a retry after its
state is durably persisted, block composition after optional progress
degradation, truncate reconciliation, or undo queue drain/shutdown state.

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

## Atomic File Failure Provenance

Shared atomic text/JSON persistence propagates an ordinary write or replace
exception unchanged when its sibling temporary file is removed successfully.
If that cleanup also fails, `AtomicWriteCleanupError` retains the original
`primary_error`, the `cleanup_error`, and the residual `temporary_path`; the
primary error is its explicit cause. Because both persistence and cleanup are
authoritative, neither failure is degraded into a warning or retried.

SQLite transaction rollback dual failure uses the existing
`SqliteTransactionCleanupError`. It exposes both `primary_error` and
`rollback_error` as `BaseException` values and uses `primary_error` as its
explicit cause. This applies uniformly to transaction-body, interruption,
commit, and rollback-only failures; message text is diagnostic, not a schema.

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

Retryable:

- daemon connection timeout
- daemon connection failure before a response is received
- other transport-layer errors represented by the daemon client

Not retryable:

- daemon response with `status=error`
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
