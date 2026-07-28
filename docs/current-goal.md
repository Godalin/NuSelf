# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Bound process-local log lock memory without destabilizing the persistent
sidecar inode used for cross-process coordination.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit sidecar and process-local lock ownership lifetimes.
2. Specify persistent filesystem and weak in-memory identities.
3. Replace strong path retention with a guarded weak-value registry.
4. Preserve one shared lock for active holders and waiters.
5. Verify idle path reclamation plus contended writes.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Sidecar lock files remain on disk and are not unlinked during normal writes.
- Active holders and waiters retain a strong reference to their shared lock.
- Registry reclamation does not alter the cross-process `flock` protocol.

## Completion Evidence

- The process-local path registry now holds `RLock` values weakly while a
  guarded lookup still returns one shared lock to active holders and waiters.
- Idle locks and their normalized path keys are reclaimed after the last
  operation releases its strong reference.
- Cross-process `.lock` sidecars remain on disk after local lock reclamation,
  preserving their stable path-to-inode coordination identity.
- Existing 50-write thread-contention coverage remains green alongside direct
  active-lock reuse and idle-path reclamation tests.
- Focused log infrastructure tests: `53 passed`.
- `.venv/bin/pytest -q`: `1549 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `3a8f054`.

## Next Review Batch

Audit lock release and file-close failures for primary-error preservation.
