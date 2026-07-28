# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Email/macOS adapter failure diagnostics cannot replace a definitive
`False` delivery result or leave the outbox entry pending for unintended repeat
delivery.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Missing email configuration, SMTP failure, osascript timeout, and non-zero
  exit diagnostics use shared observable reporting and retain `False` when
  structured logging also fails.
- The delivery loop persists `status="failed"` and increments attempts to one
  under complete failure-diagnostic storage loss; no pending entry remains for
  implicit next-tick delivery.
- Log-only delivery, explicit dry runs, and macOS-unavailable fallback keep
  their log writes authoritative because those writes are the delivery effect.
- External send, `mark_sent`, `mark_failed`, retention, adapter ordering, and
  short-circuit behavior remain authoritative and unchanged.
- Focused email, macOS, delivery-loop, and outbox tests: 56 passed.
- Final full tests: 1337 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
notification adapter failure diagnostics preserve durable delivery outcomes.
