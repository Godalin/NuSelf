# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The REPL activity projection extraction is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `cli/repl/activity.py` owns cursor reads, transcript capture inclusion,
  visibility filtering, failure classification, and activity rendering.
- The new module does not import the CLI composition root; existing root call
  sites retain aliases to the extracted operations.
- Capture and visibility remain distinct and daemon failures remain
  user-visible without exposing unrelated domain activity.
- Focused CLI and REPL activity tests: 296 passed.
- Full tests: 1249 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Move the live activity transport loop into the new REPL activity boundary, or
extract the next complete CLI composition responsibility.
