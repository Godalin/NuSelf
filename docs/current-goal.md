# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Ordinary live-chat callback failures are separate from process-control
`BaseException` values: failures remain observable while interrupts and exits
cross the send-thread boundary after subscription cleanup.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Unexpected callback `Exception` values emit
  `chat/interactive_send_failed` with compact error and exception type after
  activity drain and subscription close.
- Ordinary callback failure retains the existing non-retryable `code=1` REPL
  result and stderr message.
- Structured diagnostic storage failure falls back to a runtime warning
  without replacing that ordinary failure result.
- Callback `KeyboardInterrupt` and `SystemExit` preserve the same exception
  object, explicit cause, and traceback when re-raised on the main thread.
- Control exceptions skip auxiliary final drain, complete subscription close,
  and are not projected as ordinary chat failures.
- Main-thread `KeyboardInterrupt`, unexpected poll/renderer failures, expected
  activity degradation, and context binding retain their existing behavior.
- Focused REPL activity, turn, session-state, and CLI tests: 321 passed.
- Final full tests: 1365 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
the live-chat send thread preserves failure and control-flow semantics.
