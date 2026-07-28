# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Enforce owner-only permissions across NuSelf-owned persistence paths.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit SQLite, append-only logs, internal snapshots, and external exports.
2. Separate NuSelf-owned paths from explicitly user-selected destinations.
3. Extract a dependency-neutral private filesystem permission boundary.
4. Apply it to SQLite, logs, runtime directories, and internal append files.
5. Preserve user-selected external destination permission semantics.
6. Verify creation, existing-file hardening, sidecars, and external boundaries.
7. Run full quality gates, commit, and push.

## Out Of Scope

- Content privacy and diagnostic redaction rules are unchanged.
- Explicit user-selected exports keep their parent-directory and `umask`
  semantics; NuSelf does not silently chmod arbitrary external locations.
- Migrating or recursively rewriting historical files is not part of runtime
  path creation; active files are hardened when opened by their owner.

## Completion Evidence

- `nuself.private_fs` is the dependency-neutral owner of `0700` directory and
  `0600` regular-file creation/hardening; non-regular file targets fail without
  being chmodded.
- Shared atomic files, file collections, runtime directories, workspaces,
  thread archives and locks, reason artifacts, and internal append streams use
  the same boundary.
- SQLite main/workspace databases are secured before connection; active
  WAL/SHM sidecars and private import/export snapshots remain `0600`.
- Structured log directories, active files, rotated backups, and stable lock
  sidecars are hardened before append and remain owner-only through rotation.
- Explicit user-selected memory export destinations retain their existing
  directory and file modes.
- Focused persistence, CLI, daemon, transcript, and workspace suites:
  `529 passed`.
- Full test suite: `1656 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through implementation commit `7139497`.

## Next Review Batch

Review crash durability and directory-entry synchronization after all
NuSelf-owned persistence paths have explicit permission ownership.
