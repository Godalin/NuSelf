# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active stabilization target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](TODOs.md), not here.

## Focus

Stabilize the `v0.2.x` line using the following release plan:

1. ✅ `v0.2.1` approval decorator.
2. ✅ `v0.2.2` trace/reason schema cleanup + persona management.
3. ☐ `v0.2.3` storage interface.
4. ☐ `v0.2.4` sqlite backend.
5. ☐ `v0.2.5` migration + export/import.
6. ☐ `v0.2.6` regression tests + docs.

The `v0.2.x` line is the ongoing stabilization branch. `main` remains the stable, releasable branch, while `feature/*` stays isolated for one feature or fix at a time and then merges back into `dev/v0.2.x`.

## Immediate Context

- We are working on `dev/v0.2.x` for stabilization work.
- `v0.2.2` is the current release; next target is `v0.2.3`.
- `main` was reverted to pre-approval-decorator state; will merge `dev/v0.2.x` into `main` once the stabilization line is complete.
- Specs remain the source of truth for behavior changes.
- User-visible changes should keep README, specs, TODOs, and changelog synchronized.

## Next Steps

### ✅ P0 — v0.2.1 Approval Decorator

(Completed — released as v0.2.1.)

### ✅ P1 — v0.2.2 Schema Cleanup

(Completed — released as v0.2.2.)

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
- The branch remains aligned with `dev/v0.2.x` stabilization work and does not mix in unrelated feature experiments.
