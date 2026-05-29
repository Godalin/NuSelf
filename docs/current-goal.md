# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active stabilization target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](TODOs.md), not here.

## Focus

Stabilize the `v0.2.x` line using the following release plan:

1. `v0.2.1` approval decorator.
2. `v0.2.2` trace/reason schema cleanup.
3. `v0.2.3` storage interface.
4. `v0.2.4` sqlite backend.
5. `v0.2.5` migration + export/import.
6. `v0.2.6` regression tests + docs.

The `v0.2.x` line is the ongoing stabilization branch. `main` remains the stable, releasable branch, while `feature/*` stays isolated for one feature or fix at a time and then merges back into `dev/0.2.x`.

## Immediate Context

- We have switched to `dev/0.2.x` for stabilization work.
- `v0.2.0` is the current baseline for the stabilization line.
- The branch should absorb only release-line stabilization work, not unrelated experimental changes.
- Specs remain the source of truth for behavior changes.
- User-visible changes should keep README, specs, TODOs, and changelog synchronized.

## Next Steps

### P0 — v0.2.1 Approval Decorator

- [ ] Define the approval decorator contract and where it sits in the command/service flow.
- [ ] Create a `feature/v0.2.1-approval-decorator` branch for the approval decorator work, then merge it back into `dev/0.2.x` when complete.
- [ ] Update the relevant spec before implementation.
- [ ] Implement and test the decorator.

### P1 — v0.2.2 Schema Cleanup

- [ ] Clean up trace/reason schema boundaries.
- [ ] Update storage and rendering docs together with the schema changes.

### P2 — v0.2.3 Storage Interface

- [ ] Introduce the storage interface abstraction.
- [ ] Make repositories use the interface without changing behavior.

### P3 — v0.2.4 SQLite Backend

- [ ] Add the SQLite backend behind the storage interface.
- [ ] Keep file-backed behavior available until the migration path is ready.

### P4 — v0.2.5 Migration + Export/Import

- [ ] Add migration support.
- [ ] Add export/import tooling and docs.

### P5 — v0.2.6 Regression Tests + Docs

- [ ] Add regression coverage for the stabilized release line.
- [ ] Refresh docs to match the final v0.2.x behavior.

## Completion Criteria

- The v0.2.x stabilization line is implemented in order.
- Specs are updated before code for each non-trivial step.
- README, specs, TODOs, and CHANGELOG stay synchronized for user-visible changes.
- The branch remains aligned with `dev/0.2.x` stabilization work and does not mix in unrelated feature experiments.
