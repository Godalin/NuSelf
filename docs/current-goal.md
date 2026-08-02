# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

In progress — continuously audit and simplify while preserving composability.

## Current Phase

Restore this file as a concise active board before selecting the next code
reduction.

## Ordered Steps

1. Remove completed phase history and stale implementation descriptions from
   this active board.
2. Preserve only the persistent constraints and the latest verified baseline.
3. Verify the document contract, commit the cleanup, then inspect the next
   application/daemon reduction without pushing.

## Exclusions

- Do not move completed internal refactor history into another rolling log.
- Do not change runtime behavior in this documentation correction.
- Do not declare the persistent simplification goal complete.

## Constraints

- Preserve domain-owned registries, semantic validators, service APIs, durable
  recovery, and the single-scheduler daemon.
- Add no generic bus, facade hierarchy, compatibility shim, worker, or lock.
- Prefer deletion and direct composition over new indirection.
- Keep each reduction independently tested and committed; do not return this
  board to Idle while the persistent review goal remains active.

## Completion Evidence

- The previous configuration phase removed the parallel single-file loader in
  commit `0290bafb`; the full suite passed 2447 tests, Pyright reported 0 errors
  and 0 warnings, and both distribution artifacts built successfully.
- This board contains one active phase and one current evidence baseline;
  completed detail remains available through Git and `CHANGELOG.md`.
