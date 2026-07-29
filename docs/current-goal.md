# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make a curator source range resumable across cursor persistence failure.
Persist the exact ready decision before candidate effects, reuse deterministic
candidates, and never call the model twice for the same unfinished range.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inspect existing receipt, journal, idempotency, and transaction facilities.
2. Specify a bounded per-thread plan record for the exact ready decision.
3. Derive candidate identity from source range and action index.
4. Resume a saved plan before asking the model for a new decision.
5. Prove cursor failure reuses candidates and leaves later messages unconsumed.
6. Run focused and full quality gates, commit by functional boundary, push,
   and confirm development-branch CI.

## Out Of Scope

- No candidate, cursor, or MemoryEntry wire-schema change.
- No new StorageBackend collection or SQLite schema migration; the plan is
  cursor-adjacent curator control state.
- No replay of a plan whose typed state is corrupt or incompatible with the
  current thread.
- No process-crash atomicity claim inside one candidate acceptance operation.
- No change to candidate acceptance compensation or audit/trace policy.

## Completion Evidence

- The cursor is currently written only after every candidate action and
  auto-accept attempt complete.
- If that final atomic cursor write raises, candidate/entry effects remain
  durable but the next run has no receipt and invokes the model again.
- Existing notification idempotency and reason export IDs do not retain a
  curator action batch. Adding a StorageBackend collection would require a
  SQLite schema-version migration.
- Chosen design: one typed, atomically replaced plan per thread, stored beside
  curator cursors. It is written before candidate effects and contains the
  exact source range and actions.
- Candidate IDs are deterministic per plan action. Resume checks the candidate
  repository before resolving conflicts or staging mutations.
- `MemoryCuratorPlan` strictly round-trips thread identity, absolute source
  range, stable observation time, and normalized structured actions.
- A stale plan at or behind the cursor is ignored and can be replaced; an
  unfinished plan must start exactly at the cursor and cannot extend beyond the
  thread's known end.
- Both pending/manual-review and accepted/auto-accepted candidates are reused
  after an injected cursor write failure. The model is called once for the
  unfinished range, and messages that arrived during recovery are processed in
  the following run.
- A plan write failure occurs before candidate effects. An incompatible plan
  emits `record_decode_failed` and aborts without a model call.
- Focused curator tests: 36 passed.
- Full suite: 2179 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed.

## Publication

Pending implementation, validation, publication, and final-push CI.

## Next Review Batch

After this boundary is complete, inspect plan corruption recovery and operator
repair ergonomics across CLI and daemon surfaces.
