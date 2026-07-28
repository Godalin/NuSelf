# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. SQLite transaction rollback dual failures are structurally inspectable
while preserving the original body, commit, interruption, or rollback-only
failure and restoring transaction-local state.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `SqliteTransactionCleanupError` exposes the exact `primary_error` and
  `rollback_error` objects and retains the primary operation as explicit cause.
- Transaction-body `RuntimeError`, `KeyboardInterrupt`, commit failure, and
  rollback-only failure use the same dual-failure contract.
- Every rollback path clears the column cache and resets thread-local depth and
  rollback-only state before propagating; a recovered connection can start and
  commit a subsequent transaction.
- Exception type, message compatibility, nested transaction policy, and retry
  behavior are unchanged.
- Focused SQLite, reason service, and reason advancer tests: 89 passed.
- Final full tests: 1308 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
SQLite transaction rollback preserves structured dual failure provenance.
