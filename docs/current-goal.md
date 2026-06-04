# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active stabilization target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](TODOs.md), not here.

## Focus

Stabilize the `v0.2.x` line using the following release plan:

1. ✅ `v0.2.1` approval decorator.
2. ✅ `v0.2.2` trace/reason schema cleanup + persona management.
3. ☐ `v0.2.3` storage abstraction.
4. ☐ `v0.2.4` sqlite backend.
5. ☐ `v0.2.5` thought pack infrastructure.
6. ☐ `v0.2.6` regression tests + docs.

The `v0.2.x` line is the ongoing stabilization branch. `main` remains the stable, releasable branch, while `feature/*` stays isolated for one feature or fix at a time and then merges back into `dev/v0.2.x`.

## Immediate Context

- We are working on `dev/v0.2.x` for stabilization work.
- `v0.2.2` is the current release; next target is `v0.2.3`.
- `main` was reverted to pre-approval-decorator state; will merge `dev/v0.2.x` into `main` once the stabilization line is complete.
- Specs remain the source of truth for behavior changes.
- User-visible changes should keep README, specs, TODOs, and changelog synchronized.
- Feature branch: `feature/v0.2.3-storage-interface` (from `dev/v0.2.x`).

## Next Steps

### ✅ P0 — v0.2.1 Approval Decorator

(Completed — released as v0.2.1.)

### ✅ P1 — v0.2.2 Schema Cleanup

(Completed — released as v0.2.2.)

### P2 — v0.2.3 Storage Abstraction

- [ ] Define `StorageBackend` + `StorageCollection` protocols.
- [ ] Implement `FileStorageBackend` with collection→path mapping.
- [ ] Refactor all repositories to accept `StorageBackend` instead of `project_root`.
- [ ] Unify long-lived object ID prefixes across subsystems.
- [ ] Update CHANGELOG.md and docs.
- [ ] Run `pytest -x -q` + `uvx pyright src/ tests/` after each change.
- [ ] Merge `feature/v0.2.3-storage-interface` → `dev/v0.2.x`, tag `v0.2.3`.

### P3 — v0.2.4 SQLite Backend

- [ ] Implement `SqliteStorageBackend`.
- [ ] Define full `nuself.sqlite` schema with `structured fields + payload_json` principle.
- [ ] Add migration system + `PRAGMA user_version`.
- [ ] Support transactional trace/reason operations.
- [ ] Add workspace_entries table.
- [ ] Add optional FTS5 search backend (coexists with current scoring).
- [ ] Add `nuself dev migrate` for file→db migration.
- [ ] Default backend remains `file`; user opts in.

### P4 — v0.2.5 Thought Pack Infrastructure

- [ ] Implement `nuself pack export` (curated subset, no runtime/conf/cache).
- [ ] Implement `nuself pack import`.
- [ ] Implement `nuself pack inspect`.
- [ ] Manifest metadata + identity isolation.
- [ ] Prepare for GitHub-based NuHub sharing (future).

### P5 — v0.2.6 Regression Tests + Docs

- [ ] Add regression coverage for the stabilized release line.
- [ ] Refresh docs to match the final v0.2.x behavior.

## Completion Criteria

- The v0.2.x stabilization line is implemented in order.
- Specs are updated before code for each non-trivial step.
- README, specs, TODOs, and CHANGELOG stay synchronized for user-visible changes.
- The branch remains aligned with `dev/v0.2.x` stabilization work and does not mix in unrelated feature experiments.
