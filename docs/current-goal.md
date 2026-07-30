# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close the remaining v0.3.0 authority, managed-directory, configuration
migration, validation, and notification-cleanup findings.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Make file authority selection atomic with migration publication, reject
   file access after backend closure, and restrict authority migration to the
   canonical SQLite path.
2. Reject symlinked or non-directory managed private paths before permissions
   or external contents can be changed.
3. Add an explicit v0.2.5 configuration migration boundary, including a typed
   legacy-email migration diagnostic.
4. Make runtime validation type-strict and prove behavioral acceptance parity
   with the published JSON Schema.
5. Align notification cleanup help and behavior with explicit terminal-status
   selection.
6. Run complete concurrency, compatibility, schema, type, build, and
   clean-wheel release gates.

## Out Of Scope

- Stable `v0.3.0` promotion, release metadata, and tagging require a separate
  goal on `main`.
- Global plus directory-local configuration and package-manager publication
  remain deferred in [`TODOs.md`](TODOs.md).
- Existing documented semi-durable ThreadStore follow-ups remain deferred.

## Completion Evidence

- File authority selection now re-checks canonical SQLite authority while
  holding the shared lease; a barrier regression proves a selector paused
  before migration resumes on SQLite rather than obsolete files. Explicit
  file construction rejects published SQLite authority, closed backends and
  existing collections reject every operation, and custom migration
  destinations are removed. Focused storage/CLI verification: 87 passed;
  locked Pyright reported 0 errors and 0 warnings.
- Managed `private/` directories are now created and opened
  component-by-component with no-follow directory handles. Direct filesystem,
  config, file-storage, and SQLite regressions prove a redirected private root
  fails before changing the external target's mode or contents. Focused
  filesystem/config/storage verification: 168 passed; locked Pyright reported
  0 errors and 0 warnings.
- The frozen migration fixture now includes the byte-identical official v0.2.5
  example config. The loader removes only retired
  `experimental.langmem_adapter` with one safe warning per path and preserves
  all remaining values; enabled legacy email without a recipient raises a
  credential-safe typed migration error naming the current YAML fields.
  Focused config/email verification: 39 passed; locked Pyright reported 0
  errors and 0 warnings.
- Pending: strict runtime/schema behavioral parity and notification cleanup
  require implementation and direct regression evidence, followed by the
  complete release gate.
