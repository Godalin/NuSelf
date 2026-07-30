# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The remaining v0.3.0 external-audit findings are closed.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Discuss and specify the next objective before implementation.

## Out Of Scope

- No implementation work is active.
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
- Runtime configuration is now type-strict. A standards-compliant JSON Schema
  acceptance matrix proves identical decisions for quoted scalar types,
  bool/integer confusion, defaults, unknown shapes, enabled email fields,
  paired SMTP credentials, whitespace, and header controls. Broad
  config/notification/daemon/CLI verification: 810 passed; locked Pyright
  reported 0 errors and 0 warnings.
- Notification cleanup now accepts `sent`, `failed`, `dismissed`, or
  `all-terminal`, defaults to all terminal entries, and never deletes pending
  work. A failed-selection regression covers a persisted `uncertain` adapter
  plan. Focused notification/CLI verification: 393 passed; locked Pyright
  reported 0 errors and 0 warnings.
- Final combined verification reported 2408 passed. Locked Pyright reported 0
  errors and 0 warnings; `uv lock --check`, `git diff --check`, and the
  explicit v0.2.5 data/config compatibility gate passed.
- `uv build` produced the 0.3.0rc1 sdist and wheel. A clean Python 3.14
  environment installed only that wheel, imported `nuself.cli` and
  `nuself.llm` under fail-fast execution, and reported `nuself 0.3.0rc1`.
