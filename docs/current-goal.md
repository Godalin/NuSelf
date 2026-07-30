# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Promote the frozen `0.3.0rc1` codebase to stable `v0.3.0` through a
metadata-only release change, validate the exact release commit, and merge it
to `main` without reopening implementation review.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Confirm the frozen branch state, release metadata contract, branch
   topology, and remote tag side effects.
2. Promote package, runtime fallback, README, and changelog metadata to
   `0.3.0`.
3. Run the locked type, test, build, clean-wheel, and release-metadata gates
   against the release candidate commit.
4. Fast-forward `main`, create an annotated local `v0.3.0` tag, and verify the
   exact tagged commit and release topology.
5. Push non-publication branch updates and verify their final CI. Keep the
   remote tag and its automatic GitHub Release behind separate publication
   authorization.

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
- Pending: exact tagged-commit topology validation, `main` promotion, and final
  branch CI. Remote tag publication remains separately authorized.
