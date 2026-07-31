# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — decouple conversation from the knowledge domains for v0.3.1.

## Objective

Make conversation an optional producer at the application boundary rather than
an authority read by memory or reflection. Memory and reflection must remain
fully usable when no conversation store or chat runtime is composed.

## Ordered Steps

1. Define a one-way projection from a completed conversation turn into a
   memory-owned durable observation.
2. Replace conversation-backed memory scanning, cursors, plans, and locks with
   observation-owned ingestion and recovery state.
3. Remove recent conversation text from reflection candidate generation; use
   only memory, profile, and imported source knowledge.
4. Reduce daemon/application composition to publish and schedule observations
   without memory or reflection reading conversation state.
5. Migrate existing SQLite state without losing unprocessed durable chat input,
   update user-visible documentation, and verify all supported platforms.

## Exclusions

- Conversation may call memory/reflection tools; this consumer direction is
  intentional and does not grant either domain access to conversation state.
- Provenance may retain an opaque source reference created by the application
  projection, but knowledge-domain records must not require a conversation ID.
- This goal does not redesign the model provider or interactive presentation.

## Completion Evidence

- No production module below `nuself.memory` or `nuself.reflection` imports,
  stores, or queries conversation state, messages, stores, or IDs.
- Memory curation can recover from a process restart using only memory-owned
  storage, and reflection can run without a conversation collaborator.
- Migration, focused boundary tests, full pytest, Pyright, build, clean-wheel
  smoke, and the final six-platform CI pass.

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
