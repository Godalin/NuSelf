# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — documenting the repository PR boundary and completing the 0.4.0
release review.

## Objective

Define when NuSelf changes require a short-lived feature branch and Pull
Request, then apply the documented review and CI gates to the 0.4.0 release PR
before deciding whether it is ready to merge into `main`.

## Next Steps

1. Add the branch/PR decision rule and lightweight single-maintainer review
   gate to the authoritative development specification.
2. Commit and push the specification update to the 0.4.0 release branch.
3. Complete one Codex diff review, wait for the full CI matrix, and merge the
   release PR only if every documented gate passes.

## Exclusions

- Do not introduce CODEOWNERS, mandatory external reviewers, or enterprise
  approval ceremony.
- Do not merge while scope, review findings, tests, or CI remain unresolved.
- Do not create the release tag before the release commit is on `main`.

## Completion Evidence

- The spec distinguishes direct low-risk commits, feature PRs into the current
  minor branch, and release PRs into `main`.
- Required semantic/risk categories and pre-merge evidence are explicit.
- The policy update is committed and present in PR #3.
- PR #3 has a completed diff review and green CI before merge.
