# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Cross-process SQLite schema upgrade and backup ownership are complete.

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
- Complete local verification reported 2437 passed. Locked Pyright analyzed
  327 files with 0 errors and 0 warnings; `uv lock --check`,
  `git diff --check`, and `nuself 0.3.0rc1` passed.
- `uv build` produced the 0.3.0rc1 sdist and wheel. A clean Python 3.14.3
  environment installed only the wheel plus its declared dependencies,
  imported `nuself.cli` and `nuself.llm`, and reported `nuself 0.3.0rc1`.
- GitHub Actions run `30518768205` passed on Ubuntu and macOS with Python
  3.12, 3.13, and 3.14. Every job completed locked Pyright, the full test
  suite, distribution build, and clean-wheel smoke test for commit `a2febf9`.
