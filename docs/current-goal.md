# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

In progress — continuously audit and simplify while preserving composability.

## Current Phase

Remove redundant authority arguments from CLI application borrowing.

## Ordered Steps

1. Specify the CLI root as the sole scope-selection and runtime-lifecycle owner.
2. Rename the misleading composition helpers to parameter-free graph/backend
   borrowing operations and migrate every CLI/test caller without aliases.
3. Run focused/full gates, record the current evidence, and commit without
   pushing.

## Exclusions

- Preserve one runtime/backend/graph per CLI process and explicit infrastructure
  access to the backend.
- Do not change command syntax, selected authority, or domain service APIs.
- Do not declare the persistent simplification goal complete.

## Constraints

- Preserve domain-owned registries, semantic validators, service APIs, durable
  recovery, and the single-scheduler daemon.
- Add no generic bus, facade hierarchy, compatibility shim, worker, or lock.
- Prefer deletion and direct composition over new indirection.
- Keep each reduction independently tested and committed; do not return this
  board to Idle while the persistent review goal remains active.

## Completion Evidence

- CLI application access now consists of parameter-free `cli_application()` and
  `cli_backend()` borrowing operations. The CLI root remains the sole authority
  selector and runtime lifecycle owner; source/test/spec search finds no old
  composition names or path-bearing calls. Focused runtime/CLI/REPL tests: 579
  passed; full suite: 2446 passed; Pyright: 0 errors, 0 warnings; sdist and wheel
  build succeeded.
- The active board was restored from 1634 stale/history-heavy lines to 44 lines
  in commit `d2cd6c92`; completed detail remains available through Git and
  `CHANGELOG.md`.
