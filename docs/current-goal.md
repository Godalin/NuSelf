# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The live REPL activity transport extraction is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `cli/repl/activity.py` owns the context-bound send thread and daemon activity
  subscription open, poll, fallback, final drain, and close lifecycle.
- The CLI composition root supplies polling configuration and its compatibility
  read/presentation callbacks through one thin adapter.
- Subscription cleanup runs after normal completion, daemon delivery failure,
  keyboard interruption, and unexpected poll/presentation failure.
- Focused CLI and REPL activity tests: 301 passed.
- Full tests: 1254 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Extract the next complete CLI composition responsibility after live activity
ownership is isolated.
