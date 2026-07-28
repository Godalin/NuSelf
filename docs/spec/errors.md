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

- The chat runtime writes `chat/turn_failed` when the failure occurs inside the chat graph.
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
- The loop itself must not retry the failed operation immediately. The next
  configured scheduled iteration is the retry boundary.
- Fatal initialization failures before a worker loop starts remain daemon
  startup failures and must be surfaced to the caller.

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
[chat] turn_failed status=error thread=default request=<id> error="outer <- root"
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
