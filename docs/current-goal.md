# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Daemon client failures carry structured transport phases so REPL chat
retries only failures that can plausibly benefit from retry, while retaining
request identity and whether the daemon may already have executed the request.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `DaemonConnectionError` exposes connect, request-encode, send, receive,
  response-decode, response-identity, payload-decode, and legacy unknown
  phases while preserving concise text and the original cause.
- Every real client request failure retains its generated request id;
  retryability and possible daemon completion are derived from phase.
- Missing socket and request-encoding failures are known to precede daemon
  execution; send and later failures conservatively allow for completion.
- REPL chat retries transient transport/framing failures with the same stable
  turn id, but does not retry local request encoding or malformed typed
  success-payload schemas.
- Interactive results retain phase, daemon request id, and possible-completion
  state; `turn_retry` projects the same fields as structured metadata.
- Shutdown acknowledgement validation retains the response request id.
- Focused daemon transport, CLI chat, and CLI integration tests: 335 passed.
- Final full tests: 1358 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
daemon client failures carry structured phase and retry semantics.
