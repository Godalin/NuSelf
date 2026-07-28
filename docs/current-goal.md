# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Harden daemon reason-output export recovery so corrupt manifests, unreadable
progress, and failed retry-state persistence are explicit and cannot silently
cause duplicate or untracked composition.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Audit export job dequeue, recovery, retry, and shutdown paths.
2. [x] Update reason-output and error specifications with recovery invariants.
3. [x] Separate manifest inspection from job execution with typed outcomes.
4. [x] Make corrupt/unreadable durable state fail visibly and safely.
5. [x] Add focused recovery and persistence-failure tests.
6. [x] Run full tests, type checking, and formatting checks.
7. [ ] Commit and push in reviewable stages.

## Out Of Scope

- Changing the reason-output document format or normal composition behavior.
- Retrying immediately outside the existing scheduled retry policy.
- Treating a missing optional progress snapshot as job corruption.

## Completion Evidence

- A corrupt manifest never falls through as an ordinary pending job.
- A completed job is not recomposed.
- Failure to persist retry state is separately logged with job/thread identity.
- Worker health records the operation failure without killing the loop.
- Focused tests, full pytest, Pyright, and `git diff --check` pass.
