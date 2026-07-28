# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Unify every SQLite connection-to-path backup behind one cleanup and failure
provenance boundary.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit export, import, and migration backup implementations.
2. Specify one destination connection ownership contract.
3. Extract a shared connection-to-path backup helper.
4. Migrate runtime export, thought-pack import, and v1 backup.
5. Verify success cleanup and backup/close dual failure.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Preserve locking and atomic-rename behavior at each caller.
- Keep destination path creation in the shared boundary.
- Preserve primary backup exceptions when cleanup succeeds.

## Completion Evidence

- `_backup_connection_to_path()` is the sole production caller of SQLite's
  connection backup API.
- Runtime snapshot export, validated thought-pack import, and v1 migration
  backup all delegate destination connection ownership to that boundary.
- The helper creates destination parents, opens one destination connection,
  preserves the primary backup error, and closes exactly once.
- A dual-failure test proves `SqliteStorageBackupCleanupError` retains the
  backup error as both structured state and explicit cause while separately
  retaining the close error.
- Existing WAL export/import and v1 migration tests pass through the shared
  helper.
- `.venv/bin/pytest -q`: `1496 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `a82e9df`.

## Next Review Batch

Audit other repeated SQLite open/close blocks for shared ownership helpers.
