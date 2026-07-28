# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The top-level REPL command dispatcher extraction is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `cli/repl/dispatcher.py` owns registry matching, subsystem routing, dev
  status/logs, export routing, thread lifecycle, and unknown-command help.
- The dispatcher does not import the CLI composition root; the root wires its
  handler directly through `ReplCallbacks`.
- Existing aliases, output placement, action tuples, active-thread transitions,
  subsystem commands, export, and autosave remain covered.
- Focused dispatcher, registry, session, transcript, and CLI tests: 310 passed.
- Full tests: 1258 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Extract the next complete CLI composition responsibility after command
dispatch ownership is isolated.
