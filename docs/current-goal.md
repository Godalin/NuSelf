# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The v0.3.0 external-audit findings are closed.

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

- Functional completion is preserved in commits `fee6fcf`, `ac038fb`,
  `719d9c1`, `ce1ce64`, and `5696840`, with user-visible behavior recorded
  under `CHANGELOG.md` `Unreleased`.
- Final default verification reported 2372 passed, including direct
  multithread, multiprocess, rollback, crash-recovery, schema-parity, and
  frozen v0.2.5 migration regressions.
- Locked Pyright reported 0 errors and 0 warnings; `uv lock --check` and
  `git diff --check` passed.
- `uv build` produced the 0.3.0rc1 sdist and wheel. A clean Python 3.14
  environment installed only that wheel, imported `nuself.cli` and
  `nuself.llm`, and reported `nuself 0.3.0rc1`.
