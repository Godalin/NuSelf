# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The typed CLI entrypoint controller extraction is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `cli/entrypoints.py` owns daemon startup/selection, require-daemon handling,
  deep-link and thread preparation, and daemon/local interactive routing for
  the default, `chat`, `attach`, and `open` entrypoints.
- Chat sends and REPL execution enter through one immutable typed callback
  bundle; the controller does not implement those capabilities.
- Deep-link resolution produces an immutable open target instead of mutating
  the parsed `argparse.Namespace`.
- The CLI root binds one controller directly into `InteractiveHandlers` and
  dropped all four policy-heavy handler implementations, reducing from 427 to
  314 lines.
- Direct controller tests cover failed daemon startup, require-daemon
  rejection, daemon interactive routing, and new-thread deep-link local
  routing.
- Focused entrypoint and CLI tests: 302 passed.
- Final full tests: 1267 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Resolve the REPL header presentation contract or move to daemon composition
review.
