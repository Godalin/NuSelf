# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make developer storage commands honor backend ownership: diagnostics reuse the
CLI default backend while migration/schema commands close owned connections.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit all developer storage backend creation.
2. Specify diagnostic versus temporary backend ownership.
3. Move storage inspection to the default backend.
4. Close migration and schema SQLite backends on every return path.
5. Verify reuse and close behavior at command level.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Do not close the shared default backend inside a command handler.
- Keep migration source and destination behavior unchanged.
- Preserve existing developer command output.

## Completion Evidence

- `dev storage` reads the project default backend and delegates closure to the
  outer CLI lifecycle.
- `dev migrate` closes its owned SQLite destination after success and after a
  migration exception.
- `dev db-schema` closes its owned SQLite backend, including the empty-schema
  early return.
- `create_sqlite_backend()` exposes its concrete closeable return type.
- Production search finds `auto_backend()` only inside the storage factory and
  default-registry implementation.
- `.venv/bin/pytest -q`: `1483 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `169fe7e`.

## Next Review Batch

Audit other low-level factory callers and temporary SQLite exports.
