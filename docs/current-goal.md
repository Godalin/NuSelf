# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle — obsolete source-tree directory shells are removed.

## Objective

No active implementation objective.

## Next Steps

1. Wait for an explicitly scoped bug fix, feature, or review request.
2. Define its objective, exclusions, and completion evidence before changing
   implementation.

## Last Verification

- Removed repository-owned `__pycache__` directories, the cache-only
  `src/nuself/repl` shell, and the empty `src/nuself/migrations` directory.
- Source-tree inspection finds no remaining empty or cache directories; the
  active REPL remains under `src/nuself/cli/repl`.
- Full suite: 2447 passed; Pyright: 0 errors, 0 warnings; `nuself-0.3.1` sdist
  and wheel built successfully without regenerating bytecode caches.
