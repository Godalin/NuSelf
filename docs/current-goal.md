# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Fold curator auto-accept's `draft` to `reviewed` promotion into the candidate
acceptance commit. A promotion failure must leave the candidate pending and
restore the target rather than producing an accepted candidate with an
unreviewed or partially promoted entry.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inspect curator behavior after candidate acceptance succeeds.
2. Reproduce target reviewed-state persistence outside the acceptance commit.
3. Specify requested final target review state and quarantine preservation.
4. Promote non-quarantined targets before candidate accepted-state persistence.
5. Reuse transaction and compensation for promotion failure.
6. Run focused and full quality gates, commit by functional boundary, push,
   and confirm development-branch CI.

## Out Of Scope

- No candidate or MemoryEntry wire-schema change.
- Manual acceptance continues to produce `draft` MemoryEntry targets.
- ProfileItem targets remain unaffected by MemoryEntry review states.
- Unknown types remain quarantined rather than being forced to reviewed.
- No change to cursor or trace best-effort policy.

## Completion Evidence

- Candidate acceptance now commits target mutation and candidate final state
  through one transaction/compensation boundary.
- Curator currently calls ordinary `accept(candidate.id)`, receives a draft
  MemoryEntry, then writes a reviewed copy after candidate acceptance is final.
- If that reviewed write fails, the candidate is already accepted and cannot
  be retried through the candidate state machine; the cursor remains
  unadvanced, allowing duplicate candidate generation on the next pass.
- MemoryEntryRepository quarantine behavior must still run on the initial draft
  save before any reviewed promotion.
- `MemoryCandidateRepository.accept` and `merge` now accept an explicit final
  target review state, defaulting to `draft` for manual review.
- Curator requests `reviewed`; non-quarantined targets are promoted before the
  candidate accepted-state write.
- A failed create promotion removes the new target; a failed merge promotion
  restores the exact prior target. In both cases the candidate remains pending
  and the original exception propagates unchanged.
- Unknown target types remain quarantined even when reviewed was requested.
- Regression tests cover successful reviewed commit, quarantine preservation,
  and create/merge promotion failure compensation.
- Focused candidate repository and curator tests: 55 passed.
- Full suite: 2174 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed.
- Development-branch CI is already configured for pushes to every `dev/**`
  branch. Run `30446653041` passed Python 3.12-3.14 type checks, tests, builds,
  and clean-wheel smoke tests.

## Publication

Atomic curator auto-accept was implemented and published in `17ee110`;
development CI run `30446653041` passed.

## Next Review Batch

After this boundary is complete, inspect candidate audit/trace secondary
effects for false failure reporting after authoritative persistence.
