# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Repair the failed `v0.3.0` tagged-commit release gate without changing frozen
runtime implementation, replace the unpublished tag with a corrected release
commit, and verify the complete release workflow.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Run the release metadata verifier through the uv-synchronized environment
   and add a workflow contract regression test.
2. Run focused and complete local release gates, then create and push the
   corrective release commit on `main` and `dev/v0.3.x`.
3. Replace the failed, unpublished `v0.3.0` tag with an annotated tag on the
   corrected release commit.
4. Verify the complete tagged Release workflow and final repository state.

## Out Of Scope

- Further audit or implementation changes in storage, filesystem, config, or
  notification code unless a release gate or core CLI smoke test fails.
- Package-manager and distribution channels beyond the tag-triggered GitHub
  Release remain separately authorized.
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
- Release commit `28eea69` was fast-forwarded to `main` and
  `dev/v0.3.x`. The local annotated `v0.3.0` tag peels exactly to that commit,
  and the full release metadata and remote-main topology gate passed.
- GitHub Actions run `30522764611` passed on Ubuntu and macOS with Python
  3.12, 3.13, and 3.14. Every job completed locked Pyright, the full test
  suite, distribution build, and clean-wheel smoke test.
- The `v0.3.0` tag remains local. No GitHub Release, provenance attestation, or
  other distribution-channel publication has been started.
- The first remote tag run `30523364477` failed before Pyright, tests, build,
  attestation, or release creation because the metadata script ran under the
  system interpreter instead of the uv-synchronized environment.
- The corrected workflow contract, `uv lock --check`, `git diff --check`, the
  release metadata/topology gate, locked Pyright, and the complete 2437-test
  suite pass locally.
