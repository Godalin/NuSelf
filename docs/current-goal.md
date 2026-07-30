# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Reduce both `v0.3.0` README files from manual-sized documents to concise
project front pages, move durable user guidance into focused documents, and
replace the annotated `v0.3.0` tag after documentation validation.

## Active Branch

`main`

## Ordered Work

1. Map existing README sections to authoritative specifications and focused
   user documentation.
2. Add concise configuration, CLI, memory, and contributor guides where the
   README currently carries that responsibility.
3. Rewrite the English and Chinese READMEs to the same compact structure:
   identity, status, features, quick start, common workflows, privacy,
   limitations, and documentation.
4. Validate commands, links, bilingual structure, release metadata, and
   documentation-related tests.
5. Commit in coherent documentation boundaries, synchronize `main` and
   `dev/v0.3.x`, replace the annotated `v0.3.0` tag, and verify final CI and
   release state.

## Out Of Scope

- Runtime implementation and behavior changes.
- Package-manager and distribution channels beyond GitHub Releases remain
  separately authorized.
- Global plus directory-local configuration and package-manager publication
  remain deferred in [`TODOs.md`](TODOs.md).
- Existing documented semi-durable ThreadStore follow-ups remain deferred.

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
- Pending: branch CI, annotated tag replacement, tagged Release workflow,
  final artifact checksums, and current-goal closure.
