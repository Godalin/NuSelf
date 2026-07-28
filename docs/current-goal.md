# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Daemon lifecycle audit storage failure cannot reject instance-lock
contention, abort an otherwise valid daemon start, prevent CLI or REPL
lifecycle operations, or replace their authoritative status result.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Server ownership and CLI/REPL lifecycle records use the shared
  `daemon/lifecycle_audit_write_failed` observable projection boundary.
- Instance-lock contention still returns exit status 1 and preserves the
  owner's socket and PID when audit and diagnostic storage both fail.
- A failed `started` audit does not prevent worker startup, orderly cleanup,
  the post-cleanup `stopped` projection, or a successful daemon result.
- One-shot start, stop, and restart retain lifecycle calls, status output, and
  exit decisions under complete audit-storage loss.
- Interactive restart still performs stop then start, preserves the session,
  and reports the running daemon under complete audit-storage loss.
- Focused daemon-instance and CLI tests: 309 passed.
- Final full tests: 1340 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
daemon lifecycle audits preserve authoritative lifecycle outcomes.
