# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make each acknowledged structured-log append crash-durable.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit append, synchronization, rollback, close, and observer ordering.
2. Define acknowledgment only after the complete JSONL record is synced.
3. Make rollback truncate and sync the prior durable boundary.
4. Replace ambiguous persistence booleans with explicit outcome states.
5. Deliver observers only after durable append and successful handle close.
6. Verify write/sync and truncate/sync failures plus lifecycle provenance.
7. Run full quality gates, commit, and push.

## Out Of Scope

- SQLite durability remains governed by SQLite journal and synchronous modes.
- No asynchronous batching or resident flush queue is introduced; each event
  remains an independent append transaction.
- SQLite and non-log append streams retain their subsystem-specific durability
  contracts.

## Completion Evidence

- The logs directory is synchronized before every append, covering new active
  names, post-rotation files, and retry after an earlier directory-sync failure.
- Each complete JSONL record is written with short-write handling and `fsync`ed
  before close and observer delivery.
- Write or append-sync failure triggers `truncate` plus `fsync` back to the
  captured durable boundary; successful rollback preserves the original error.
- Rollback failure emits the existing content-safe warning and raises
  `LogAppendLifecycleError` with `persistence_outcome="uncertain"`.
- Close failure after successful append sync reports
  `persistence_outcome="persisted"` and suppresses observer delivery.
- The former ambiguous `record_may_have_persisted` boolean is removed from
  implementation, tests, and specifications.
- Focused logging and observability suites: `88 passed`.
- Full test suite: `1665 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through implementation commit `e2b72ec`.

## Next Review Batch

Review structured-log batching and throughput policy after individual append
transactions have a truthful crash-durable contract.
