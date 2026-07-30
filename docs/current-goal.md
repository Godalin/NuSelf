# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The `v0.3.0` README refresh and release replacement are complete.

## Active Branch

None.

## Ordered Work

No active work.

## Out Of Scope

No active scope.

## Completion Evidence

- English README reduced from 954 to 209 lines; Chinese README reduced from
  879 to 189 lines. Both retain the same project-front-page information
  architecture and remain below the enforced 250-line limit.
- Configuration, CLI, memory, and contributor guidance now lives in focused
  documents. Local-link validation covers all six user-facing entry points.
- CLI examples were checked against the v0.3.0 parser help; stale README
  options such as `--content`, `--by-index`, and notification/reflection
  `-i` selection were removed.
- `uv lock --check`, `git diff --check`, v0.3.0 release metadata validation,
  and `nuself 0.3.0` passed.
- Complete local verification reported 2439 passed. Locked Pyright reported
  0 errors and 0 warnings.
- `uv build` produced the v0.3.0 sdist and wheel. A clean Python 3.14.3
  environment installed the wheel, reported `nuself 0.3.0`, and confirmed the
  compact README is embedded in package metadata.
- Branch CI run `30526417504` passed on Ubuntu and macOS with Python 3.12,
  3.13, and 3.14.
- The annotated `v0.3.0` tag now resolves to `d31502f`. Tagged Release run
  `30526689042` passed its full release gate.
- The final GitHub Release contains only the wheel, source archive, and
  `SHA256SUMS`; downloaded artifacts passed their published checksums.
