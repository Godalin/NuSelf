# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Migrate this checkout's legacy `private/` authority to `./.nuself`, verify the
new authority, remove the confirmed-obsolete source, and rename the public
example layout to match v0.3.1.

## Active Branch

`main`

## Ordered Work

1. [complete] Audit source/target state and active daemon/storage ownership.
2. [complete] Migrate `private/` to `./.nuself` through the supported explicit command.
3. [complete] Verify record counts, configuration, SQLite integrity, and local CLI access.
4. [complete] Remove the preserved legacy source only after verification.
5. [complete] Rename `examples/private/` to `examples/.nuself/` and update governing
   documentation and references.
6. [complete] Run focused and complete gates, commit coherently, and return this board to
   idle.

## Completion Evidence

- Old and new SQLite `quick_check`: `ok`; all 12 collection counts matched.
- New local CLI selected `./.nuself/nuself.sqlite`; non-transient file
  comparison found no differences.
- Migration and release-contract focus: 13 passed; focused Pyright clean.
- Complete unit suite and full-source Pyright passed.
- Migrated local daemon is ready on authority
  `v1-804dd793a3f3e50e33a95343`.
