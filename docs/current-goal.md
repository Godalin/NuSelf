# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle — no active implementation goal.

## Completed Evidence

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
