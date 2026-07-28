# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The REPL interactive turn coordinator extraction is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `cli/repl/turns.py` owns stable turn identity, bounded retry, exact runtime
  context, live activity coordination, session capture, presentation order,
  and duplicate error suppression.
- The root supplies retry/poll settings plus activity/reply effects through one
  thin adapter; the turns module does not import the CLI composition root.
- Direct tests prove retry identity, ambient-context isolation/restoration,
  transcript association, retry-log correlation, and reply presentation.
- Focused turns, activity, session, and CLI tests: 312 passed.
- Full tests: 1259 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Extract the next complete CLI composition responsibility after turn
coordination is isolated.
