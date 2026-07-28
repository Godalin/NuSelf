# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The CLI parser now injects only dynamic chat entrypoint policy; reason
watch is owned and bound directly by the REPL command subsystem.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- The argparse reason-watch adapter lives with the REPL reason-watch command.
- The parser binds reason watch directly without routing it through the CLI
  composition root.
- `EntrypointHandlers` now contains only default/chat/attach/open callbacks
  backed by the configured `EntrypointController`.
- Activity reader/presenter effects remain explicit testable dependencies and
  are no longer described as compatibility callbacks.
- A parser-dispatch regression test verifies project root, interval, and thread
  selection reach the REPL command owner.
- Focused reason-watch test: 1 passed.
- Final full tests: 1378 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit explicit legacy persisted-data fallbacks, removing only those without a
current migration contract.
