# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Lock-aware live SQLite authority validation is complete.

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

- Canonical authority identity now uses lock-aware `mode=ro` access and a
  metadata-only validator; thought-pack import and inspection retain the
  separate full `quick_check` integrity boundary.
- Ordinary live close uses a cooperative passive checkpoint, while only the
  exclusive unpublished migration backend requires a truncating checkpoint.
  Explicit external SQLite opens preserve parent and database modes.
- Cross-process regressions continuously commit and checkpoint while another
  process repeatedly opens, reads, and closes authority, and recover a
  committed uncheckpointed WAL after abrupt writer exit.
- Focused storage, private-filesystem, and CLI verification reported 143
  passed. Locked Pyright reported 0 errors and 0 warnings; `git diff --check`
  passed.
- Complete local verification reported 2430 passed. Locked Pyright analyzed
  327 files with 0 errors and 0 warnings; `uv lock --check`,
  `git diff --check`, and `nuself 0.3.0rc1` passed.
- `uv build` produced the 0.3.0rc1 sdist and wheel. A clean Python 3.14.3
  environment installed only the wheel plus its declared dependencies,
  imported `nuself.cli` and `nuself.llm`, and reported `nuself 0.3.0rc1`.
- GitHub Actions run `30517226479` passed on Ubuntu and macOS with Python
  3.12, 3.13, and 3.14. Every job completed locked Pyright, the full test
  suite, distribution build, and clean-wheel smoke test for commit `53605cd`.
