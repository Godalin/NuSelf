# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle — conversation/knowledge API decoupling is complete for v0.3.1.

## Objective

No active implementation objective.

## Ordered Steps

1. Await the next approved goal.

## Exclusions

- No new work is implied while this board is idle.

## Completion Evidence

The conversation/knowledge API refactor is complete in `377a65e`:

- `ApplicationGraph` owns a bounded, read-only conversation history service;
  reflection consumes immutable excerpts rather than conversation storage,
  state, locks, or schema.
- Completed turns cross into memory only through a generic durable observation
  API. Curator recovery, plans, locks, daemon scans, and manual updates are all
  observation-owned and no longer scan conversations.
- Schema v7 preserves unprocessed v6 evidence. The project-local database was
  migrated with its pre-v7 backup retained; `PRAGMA quick_check` returned
  `ok`, conversations remained readable, and old cursors became observations.
- Pyright completed with 0 errors and 0 warnings; all 2436 tests, lock check,
  sdist/wheel build, supported-Python clean-wheel install, import, and CLI
  smoke tests passed. Final remote CI remains the branch push gate.

## Previous Completed Evidence

The v0.3.1 persistent-conversation refactor is complete in `e656b19`:

- `conversation`, `session`, and `turn` now have distinct contracts; reason
  threads retain their separate `reason_id` identity.
- Neutral conversation state/storage is owned once by `ApplicationGraph`, so
  memory and reflection no longer import the chat agent implementation.
- Reversible schema v6 migration preserves records and rejects collection
  collisions atomically. The project authority migrated from v5 to v6 with a
  retained pre-migration backup and `PRAGMA quick_check = ok`.
- Replies commit and render before compression; daemon memory curation and
  compression share the conversation resource with curation ordered first.
- Turn completion records bounded stage durations and context counts without
  prompt, message, memory, or summary content.
- Pyright completed with 0 errors and 0 warnings; 2439 tests and both sdist and
  wheel builds passed. Final remote CI remains the release-branch push gate.
