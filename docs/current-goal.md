# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Recoverable local `:persona` and `:history` failures now retain concise
interactive results while writing privacy-bounded structured diagnostics.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `:persona` writes `persona/interactive_command_failed` with only the command
  action; prompt text and other command arguments are excluded.
- `:history` writes `chat/interactive_history_load_failed` with the requested
  thread ID and compact exception chain.
- Both diagnostics use error severity while preserving the existing rendered
  command result and interactive-session behavior.
- Structured logging failure falls back to `RuntimeWarning` without replacing
  the original command error.
- `KeyboardInterrupt` remains the same propagated object and produces no
  command-failure diagnostic.
- Focused local REPL error-boundary tests: 8 passed.
- Final full tests: 1376 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit daemon diagnostic-context lookup and remaining REPL/CLI broad exception
boundaries without adding blanket command catches.
