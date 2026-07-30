# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make SQLite the only authoritative structured-data store for both user and
workspace scopes. Migrate and verify the repository's `.nuself` data, discard
the unused legacy user authority, remove file-backed runtime storage, and add
safe user-facing data inspection and editing commands.

## Active Branch

`main`

## Ordered Work

1. Specify the SQLite-only authority boundary, migration/deletion contract,
   and validated `nuself data` CLI. **Complete.**
2. Move remaining authoritative JSON state (chat threads, curator cursors and
   plans, and scheduler state) behind SQLite repositories. **Complete.**
3. Migrate and verify the repository `.nuself`; remove the explicitly
   disposable legacy user authority and reinitialize it as SQLite.
   **Complete; discarded inputs remain temporarily recoverable outside their
   runtime paths until final verification.**
4. Remove `FileStorageBackend`, runtime fallback selection, obsolete migration
   commands, fixtures, and documentation. **Complete.**
5. Add safe list/show/edit/delete/export data services and CLI handlers.
   **Complete; final gate review pending.**
6. Update `examples/`, both READMEs, architecture, specifications, and the
   `Unreleased` changelog. **Complete.**
7. Run focused tests after each commit, then Pyright, the complete default
   suite, build, clean-wheel smoke tests, and final six-platform CI.
   **In progress.**

## Out Of Scope

- Direct SQL editing as a supported user interface.
- Moving human-edited configuration, raw source files, logs, exports/imports,
  runtime coordination files, or rebuildable caches into SQLite.
- Preserving runtime compatibility with file-backed collection authorities.

## Completion Evidence

Pending. Completion requires a SQLite-only runtime, verified project and user
authorities, no legacy collection JSON, validated data-editing workflows,
updated examples/docs, and all local/release gates passing.
