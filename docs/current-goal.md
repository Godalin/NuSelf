# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Give workspace SQLite initialization and batches one explicit connection,
transaction, and failure-provenance boundary.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit every `SqliteStore` connection, transaction, and cleanup path.
2. Specify initialization and batch ownership contracts.
3. Extract shared connection cleanup and transactional execution boundaries.
4. Preserve primary failures across rollback and close failures.
5. Verify commit, rollback, and close behavior under dual failures.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep LangGraph `BaseStore` sync and async behavior unchanged.
- Preserve one fresh SQLite connection per batch.
- Do not merge workspace storage into the long-lived storage backend.

## Completion Evidence

- `_run_transaction()` is the sole workspace SQLite connection owner for
  schema initialization and LangGraph store batches.
- The boundary opens and closes exactly once, commits successful operations,
  and rolls back operation or commit failures.
- `SqliteStoreLifecycleError` retains the primary, rollback, and close errors;
  the primary error remains the explicit cause when cleanup also fails.
- Tests cover strict-JSON operation failure combined with rollback and close
  failures, commit failure with successful cleanup, and close failure after a
  committed batch.
- Focused workspace/store tests: `22 passed`.
- `.venv/bin/pytest -q`: `1499 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `d991255`.

## Next Review Batch

Audit the remaining internal handler and error-propagation boundaries.
