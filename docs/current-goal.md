# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The remaining v0.3.0 release-preparation findings are closed.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Discuss and specify stable `v0.3.0` promotion before changing release
   metadata or `main`.

## Out Of Scope

- Stable `v0.3.0` promotion, release metadata, merging to `main`, tagging, and
  package publication remain separate explicitly authorized release actions.
- Global plus directory-local configuration and package-manager publication
  remain deferred in [`TODOs.md`](TODOs.md).
- Existing documented semi-durable ThreadStore follow-ups remain deferred.

## Completion Evidence

- SQLite creation is now migration-private and limited to unpublished
  temporary databases; runtime and direct backend opening require an existing
  regular file. `dev db-schema` reuses the CLI-owned active backend and fails
  on file authority without creating canonical SQLite or hiding an existing
  record. The frozen v0.2.5 fixture now loads its historical config, migrates
  through the exclusive atomic authority switch, reopens through
  `auto_backend()`, decodes every current repository record, and proves file
  authority cannot be reacquired. Focused release-storage verification:
  135 passed; locked Pyright reported 0 errors and 0 warnings.
- Every strict configuration model now rejects non-finite numbers, with YAML
  regressions for positive infinity, negative infinity, and NaN across both
  provider and chat timeout fields. Published-schema tests select and check
  the validator from the document's declared Draft 7 dialect before comparing
  acceptance. Focused configuration verification: 44 passed; locked Pyright
  reported 0 errors and 0 warnings.
- The notification CLI lifecycle regression now explicitly selects the
  deterministic log adapter instead of invoking the host macOS notification
  service, so the release gate does not depend on an interactive desktop.
- Final local verification reported 2418 passed. Locked Pyright reported 0
  errors and 0 warnings; `uv lock --check`, `git diff --check`, the
  byte-identical official v0.2.5 config fixture check, and
  `nuself 0.3.0rc1` passed.
- `uv build` produced the 0.3.0rc1 sdist and wheel. A clean Python 3.14
  environment installed only the wheel, imported `nuself.cli` and
  `nuself.llm`, and reported `nuself 0.3.0rc1`.
- GitHub Actions run `30514114057` passed on Ubuntu and macOS with Python
  3.12, 3.13, and 3.14. Every job completed locked Pyright, the full test
  suite, distribution build, and clean-wheel smoke test for commit `f021ba7`.
