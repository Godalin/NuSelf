# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Stable `v0.3.0` is tagged, validated, and published as a GitHub Release.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Discuss and specify the next development goal before implementation.

## Out Of Scope

- Further audit or implementation changes in storage, filesystem, config, or
  notification code unless a release gate or core CLI smoke test fails.
- Package-manager and distribution channels beyond GitHub Releases remain
  separately authorized.
- Global plus directory-local configuration and package-manager publication
  remain deferred in [`TODOs.md`](TODOs.md).
- Existing documented semi-durable ThreadStore follow-ups remain deferred.

## Completion Evidence

- Release metadata, runtime fallback, lockfile, both READMEs, and the dated
  changelog section agree on `0.3.0`; `Unreleased` is empty.
- `uv lock --check`, `git diff --check`, the metadata-only release gate, and
  `nuself 0.3.0` passed.
- Complete local verification reported 2437 passed. Locked Pyright reported
  0 errors and 0 warnings.
- `uv build` produced `nuself-0.3.0.tar.gz` and
  `nuself-0.3.0-py3-none-any.whl`.
- A clean Python 3.14.3 environment installed only the built wheel plus its
  declared dependencies, imported `nuself.cli` and `nuself.llm`, and reported
  `nuself 0.3.0`.
- GitHub Actions run `30522764611` passed on Ubuntu and macOS with Python
  3.12, 3.13, and 3.14. Every job completed locked Pyright, the full test
  suite, distribution build, and clean-wheel smoke test.
- The first remote tag run `30523364477` failed before Pyright, tests, build,
  attestation, or release creation because the metadata script ran under the
  system interpreter instead of the uv-synchronized environment.
- The corrected workflow contract, `uv lock --check`, `git diff --check`, the
  release metadata/topology gate, locked Pyright, and the complete 2437-test
  suite pass locally.
- Corrective release commit `f01529b` is on `main` and `dev/v0.3.x`. The
  remote annotated `v0.3.0` tag peels exactly to that commit.
- GitHub Actions Release run `30524026240` passed the metadata/topology gate,
  locked Pyright, complete test suite, distribution build, clean-wheel smoke,
  checksum generation, build-provenance attestation, and GitHub Release
  creation.
- The final non-draft, non-prerelease GitHub Release contains only the
  `0.3.0` wheel, sdist, and `SHA256SUMS`. Downloaded release artifacts pass
  the published checksums.
- No package-manager or other distribution-channel publication was performed.
