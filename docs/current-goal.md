# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Migrate NuSelf to reversible schema v4 with one compact records table, make
workspace state part of the main authority, and clean the repository-local
`.nuself` after verified migration.

## Active Branch

Current working branch.

## Ordered Work

1. Specify schema v4 and the compact authority layout.
2. Implement and test reversible v3↔v4 scripts.
3. Replace dynamic collection tables with the unified runtime records table.
4. Move reason exports out of workspace directories and remove obsolete
   workspace filesystem creation.
5. Migrate and verify the repository-local `.nuself`, then remove only
   superseded workspace artifacts.
6. Run full gates and commit schema/runtime and layout/data cleanup separately.

## Out Of Scope

- Deleting explicit exports, transcripts, logs, sources, or historical backups.
- Migrating the default user authority outside this repository.
- Release publication.

## Completion Evidence

Pending.
