# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Replace immutable authority inspection with lock-aware live-database identity
validation, without putting full-database integrity scans on ordinary startup.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Separate lightweight authority identity from thought-pack integrity checks
   and open live authority read-only with normal SQLite locking and WAL
   coordination.
2. Preserve owner-only hardening only for project-managed canonical and
   migration databases; explicit external SQLite paths retain their directory
   and file permissions.
3. Add cross-process writer/checkpoint/open stress coverage and an
   uncheckpointed-WAL recovery regression.
4. Run complete release gates, push the functional commits, and require the
   final six-platform CI matrix before returning this board to idle.

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
- Push and final six-platform CI are pending.
