# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The frozen `0.3.0rc1` codebase has been promoted to the validated stable
`v0.3.0` release commit.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Await separate authorization before pushing the local `v0.3.0` tag, which
   automatically starts the GitHub Release publication workflow.

## Out Of Scope

- Further audit or implementation changes in storage, filesystem, config, or
  notification code unless a release gate or core CLI smoke test fails.
- Pushing `v0.3.0`, which automatically invokes the GitHub Release workflow,
  and any package-manager or other distribution-channel publication until
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
- Release commit `28eea69` was fast-forwarded to `main` and
  `dev/v0.3.x`. The local annotated `v0.3.0` tag peels exactly to that commit,
  and the full release metadata and remote-main topology gate passed.
- GitHub Actions run `30522764611` passed on Ubuntu and macOS with Python
  3.12, 3.13, and 3.14. Every job completed locked Pyright, the full test
  suite, distribution build, and clean-wheel smoke test.
- The `v0.3.0` tag remains local. No GitHub Release, provenance attestation, or
  other distribution-channel publication has been started.
