# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make v1-to-v2 SQLite upgrade single-writer across processes and apply explicit
managed/external ownership to every backup path.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Add a stable database-path schema-upgrade lease; after acquiring it,
   re-read the version and let only the remaining v1 owner back up and upgrade.
2. Carry managed ownership through v1 backup and public `backup_to()`, keeping
   external parent and database permissions unchanged.
3. Make direct canonical construction infer managed protection and add
   concurrent-first-open, backup-content, permission, and symlink regressions.
4. Run complete release gates, push the functional commits, and require the
   final six-platform CI matrix before returning this board to idle.

## Out Of Scope

- Stable `v0.3.0` promotion, release metadata, merging to `main`, tagging, and
  package publication remain separate explicitly authorized release actions.
- Global plus directory-local configuration and package-manager publication
  remain deferred in [`TODOs.md`](TODOs.md).
- Existing documented semi-durable ThreadStore follow-ups remain deferred.

## Completion Evidence

- Existing v1 authority acquires a stable sibling schema lease before its
  writable connection setup, re-reads the version under the lease, and lets
  only the remaining v1 holder create the backup and upgrade.
- Six simultaneous first-open processes all succeed; the main database has
  exactly versions 1 and 2, while the single `.v1.bak` remains v1 with its
  payload column and source record.
- Direct canonical construction infers managed protection. External v1
  upgrade and public backup destinations preserve directory and file modes;
  managed thought-pack export/import retains owner-only modes.
- Focused storage, private-filesystem, and CLI verification reported 150
  passed. Locked Pyright reported 0 errors and 0 warnings; `git diff --check`
  passed.
- Complete local release gates, distribution verification, push, and final
  six-platform CI are pending.
