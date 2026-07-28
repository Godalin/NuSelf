# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. REPL top-level commands now use one typed, sealed handler registry owned
by the CLI composition root.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- The authoritative catalog indexes unique canonical names and aliases, and
  resolves each input once to a canonical name plus argument body.
- `ReplCommandDispatcher` owns a sealed `HandlerRegistry` with exactly one
  handler for every catalog command; composition rejects a missing or extra
  handler.
- The CLI composition root creates one dispatcher per interactive loop instead
  of using a process-global mutable registry.
- Argparse and LangChain tool dispatch remain on their framework-native
  boundaries.
- Focused REPL/CLI tests: 338 passed.
- Final full tests: 1273 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing runtime context, observability, event, and audit-log adoption
after this handler boundary is complete.
