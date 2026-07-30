# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close the final v0.3.0 SQLite authority blockers: reject redirected managed
parents before any database side effect, and refuse to adopt an empty,
unrelated, or malformed canonical SQLite file.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Validate the managed database parent and final file type before any chmod,
   SQLite connection, schema mutation, or sidecar creation.
2. Require every opened database to prove NuSelf schema identity through a
   read-only connection before reopening it for controlled v1/v2 operation;
   keep new database initialization migration-private.
3. Add side-effect-free symlink-parent regressions for both automatic and
   explicit open paths plus empty, unrelated, malformed, and v1 upgrade cases.
4. Run complete release gates, push the functional commits, and require the
   final six-platform CI matrix before returning this board to idle.

## Out Of Scope

- Stable `v0.3.0` promotion, release metadata, merging to `main`, tagging, and
  package publication remain separate explicitly authorized release actions.
- Global plus directory-local configuration and package-manager publication
  remain deferred in [`TODOs.md`](TODOs.md).
- Existing documented semi-durable ThreadStore follow-ups remain deferred.

## Completion Evidence

- Managed SQLite parent validation now precedes every file operation, and
  existing authority identity is checked through a read-only immutable
  connection before chmod, writable open, PRAGMA, schema upgrade, or sidecar
  creation. New database initialization remains migration-private.
- Automatic and explicit opening regressions prove a symlinked managed parent
  leaves the external database bytes, file and directory modes, tables, and
  sidecars unchanged. Empty, unrelated, and incomplete canonical databases
  also fail closed without mutation, while supported NuSelf databases retain
  controlled upgrade and concurrent-open behavior.
- Focused storage verification reported 139 passed. Locked Pyright reported 0
  errors and 0 warnings; `git diff --check` passed.
- Complete local verification reported 2426 passed. Locked Pyright reported 0
  errors and 0 warnings; `uv lock --check`, `git diff --check`, the frozen
  v0.2.5 migration fixture coverage, and `nuself 0.3.0rc1` passed.
- `uv build` produced the 0.3.0rc1 sdist and wheel. A clean Python 3.14
  environment installed only the wheel plus its declared dependencies,
  imported `nuself.cli` and `nuself.llm`, and reported `nuself 0.3.0rc1`.
- Push and final six-platform CI are pending.
