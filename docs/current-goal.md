# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make the durable candidate the curator's authoritative success boundary.
Auto-accept failures after that point must remain observable without preventing
cursor advancement and replaying the same source into duplicate candidates.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Verify candidate audit and memory trace failures are already isolated.
2. Reproduce an ordinary auto-accept storage failure after candidate save.
3. Define candidate durability as the authoritative curation boundary.
4. Degrade ordinary auto-accept exceptions through the registered audit event.
5. Prove the cursor advances and the source is not sent to the model twice.
6. Run focused and full quality gates, commit by functional boundary, push,
   and confirm development-branch CI.

## Out Of Scope

- No candidate, cursor, or MemoryEntry wire-schema change.
- No suppression of process-control `BaseException` subclasses.
- No claim that a double failure leaves the target repaired; it remains
  observable for operator intervention.
- No change to candidate acceptance transaction or compensation mechanics.
- No change to audit/trace best-effort policy, which is already correct.

## Completion Evidence

- Candidate audit persistence already uses the shared best-effort log
  projection. Existing failure injection proves audit sink failure cannot
  replay a committed candidate.
- Memory trace recording already runs through `run_memory_observed`. Existing
  failure injection proves trace and diagnostic sink failure cannot replace a
  reviewed entry or replay its source.
- The candidate is saved before `_auto_accept`, so it is already a durable,
  reviewable curation result when auto-accept begins.
- `_auto_accept` previously caught only `ValueError` and
  `MemoryEntryNotFound`; an `OSError` prevented cursor persistence and caused
  the same source range to be modeled again.
- Auto-accept now degrades every ordinary `Exception` through the registered
  `auto_accept_failed` event. `BaseException` remains outside that boundary.
- Regression tests inject both a storage failure and
  `MemoryCandidateCommitError`; each leaves one pending candidate, advances the
  cursor, emits the failure event, and calls the model only once.
- Focused curator tests: 32 passed.
- Full suite: 2175 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed.
- The full gate exposed a pre-existing cross-thread log-order assumption in
  the daemon join-timeout test. The test now selects the unique
  `thread_timeout` event by identity; its focused test and the full suite pass.

## Publication

Pending implementation, validation, publication, and final-push CI.

## Next Review Batch

After this boundary is complete, inspect cursor persistence failure itself;
candidate durability and cursor durability still do not share one transaction.
