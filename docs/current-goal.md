# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Validate external thought packs read-only before import and reject corrupt,
foreign, or future-schema databases without mutating the source.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit schema identity, version handling, and current import behavior.
2. Specify read-only integrity and compatibility validation.
3. Share one schema-version constant with runtime initialization.
4. Validate and backup from the same read-only source connection.
5. Verify corrupt, foreign, future, legacy, WAL, and valid inputs.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Do not migrate or otherwise modify the external source file.
- Keep imported packs inert under `private/imports`.
- Do not accept partial NuSelf schemas.

## Completion Evidence

- Import opens the source through SQLite `mode=ro`; it never constructs a
  mutable backend for the external file.
- Validation requires `quick_check=ok`, a supported non-empty schema version,
  all known collection tables, and an `id` primary key on every table.
- Validation and online backup share one source connection; destination writes
  use a unique temporary database and atomic rename.
- Validation failure creates no imported file, while cleanup always attempts
  removal of the temporary database.
- Tests reject corrupt bytes, foreign SQLite, partial schemas, and future
  versions; supported v1 sources and copies remain v1 and live WAL data is
  preserved.
- Ordinary `SqliteStorageBackend` initialization also rejects future versions.
- `.venv/bin/pytest -q`: `1491 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `a1880da`.

## Next Review Batch

Make thought-pack inspect use the same read-only validator instead of opening a
mutable backend.
