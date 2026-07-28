# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make thought-pack inspection share the read-only validator and report
collection counts without initializing or migrating the inspected database.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit inspect output and mutable backend side effects.
2. Specify read-only inspection and validation reuse.
3. Add a structured thought-pack inspection value.
4. Migrate CLI rendering off mutable `SqliteStorageBackend`.
5. Verify legacy, corrupt, WAL, count, and connection-close behavior.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Preserve existing inspect path resolution and output layout.
- Do not migrate supported legacy packs during inspection.
- Keep validation rules identical between import and inspect.

## Completion Evidence

- `ThoughtPackInspection` carries immutable schema-version and per-collection
  count data with a derived total.
- `inspect_sqlite_thought_pack()` and import share the same read-only
  connection owner and compatibility validator.
- CLI inspection renders only the structured inspection value and never
  creates `SqliteStorageBackend` for the inspected file.
- Tests prove v1 database bytes remain unchanged, corrupt packs fail, committed
  WAL rows are counted, and the read-only source connection closes once.
- Existing pack path resolution and human-readable count layout remain intact.
- `.venv/bin/pytest -q`: `1495 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `30bc7db`.

## Next Review Batch

Extract shared SQLite connection ownership helpers from pack operations.
