# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make Memory candidate acceptance one recoverable logical commit. A failure
after target create/merge/delete but before candidate `accepted` persistence
must not leave a pending candidate paired with a silently mutated durable
target.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Scan multi-write persistence paths for partial commit behavior.
2. Reproduce candidate target mutation followed by accepted-state write
   failure.
3. Specify transaction and compensation behavior for each candidate action.
4. Wrap create, merge/update, and delete acceptance in backend transactions.
5. Compensate file-backed target mutation and retain double failures.
6. Run focused and full quality gates, commit by functional boundary, push,
   and confirm development-branch CI.

## Out Of Scope

- No candidate state or wire-schema change.
- No process-crash atomicity claim for the multi-file backend.
- No silent suppression of either the accepted-state write failure or a
  compensation failure.
- No change to reject/edit operations, which mutate one candidate record.
- No change to curator auto-accept policy.

## Completion Evidence

- `accept(create)` writes a new MemoryEntry/ProfileItem before the candidate is
  marked accepted.
- `accept(update|merge)` overwrites the target before the candidate final-state
  write; retry can append source references and evidence again.
- `accept(delete)` deletes the target before the candidate final-state write;
  retry then fails because the target no longer exists.
- SQLite transactions can roll these writes back, but the repository does not
  currently enter one; file-backend transactions only serialize writes and
  require explicit compensation for in-process failures.
- Accept create, merge/update, and delete now run inside the shared backend
  transaction.
- If the accepted-state write fails, create removes its new target, merge
  restores the exact prior target, and delete restores its removed target.
- Successful compensation propagates the original exception unchanged and
  leaves the candidate pending.
- `MemoryCandidateCommitError` retains `primary_error` and
  `compensation_error`, chained from the primary failure, when rollback also
  fails.
- Regression tests cover MemoryEntry and ProfileItem creation, entry merge,
  entry deletion, exact original exception identity, and double failure.
- Focused candidate repository and curator tests: 51 passed.
- Full suite: 2170 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed.
- Development CI run `30441324777` passed all Python 3.12-3.14 jobs, builds,
  and clean-wheel smoke tests, but reported that checkout/setup-python v4 use
  the deprecated Node 20 action runtime.
- Official current action generations were verified before updating CI and
  release to `actions/checkout@v7` and `actions/setup-python@v6`.
- Workflow YAML parsing passed. Development CI run `30445870397` passed all
  matrix, build, and wheel-smoke jobs on the new actions without the prior
  Node 20 deprecation annotation.

## Publication

Recoverable Memory candidate acceptance was implemented in `651c134`; current
action runtimes were adopted in `9fd2e02`. Both were published through
`afb5f2f`, and the resulting development CI run passed.

## Next Review Batch

After this boundary is complete, inspect curator auto-accept's post-accept
review-state promotion for the same partial-success classification.
