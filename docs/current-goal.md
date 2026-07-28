# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make thought-pack export produce a consistent SQLite snapshot under WAL and
concurrent writers instead of copying only the main database file.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit remaining low-level backend and SQLite construction.
2. Specify online snapshot and destination ownership.
3. Add a locked SQLite `backup_to` boundary.
4. Migrate `pack export` from file copy to the project default backend.
5. Verify uncheckpointed WAL data and destination connection closure.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep pack import as an inert file copy into the imports directory.
- Keep pack inspect's temporary backend explicitly closed.
- Preserve existing export paths and command output.

## Completion Evidence

- `SqliteStorageBackend.backup_to()` runs SQLite online backup while holding
  the source lock and rejects a source-equal destination.
- The backup operation owns and closes each destination connection; dual
  backup/cleanup failure retains the backup error as the cause.
- `pack export` resolves the shared project SQLite backend and no longer calls
  `shutil.copy2` for the live database.
- Tests prove committed uncheckpointed WAL data is exported, repeated export
  updates an existing destination, and every destination connection closes
  once.
- A command-level test reopens the exported pack and reads data written through
  the live default backend.
- `.venv/bin/pytest -q`: `1485 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `e48cbd6`.

## Next Review Batch

Audit thought-pack import validation before accepting an external database.
