# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close the shutdown-versus-readiness race. If daemon shutdown is requested while
workers are starting, the process must enter cleanup rather than publish
`daemon/started` merely because every worker thread remains temporarily alive.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Evaluate whether one last-attempt timestamp can represent all worker modes.
2. Reject misleading staleness semantics that omit export reconciliation and
   idle queue behavior.
3. Inspect shutdown interaction with the existing readiness check.
4. Specify shutdown as a negative readiness condition.
5. Reject readiness through the same typed supervisor boundary.
6. Run focused and full quality gates, commit by functional boundary, push,
   and confirm development-branch CI.

## Out Of Scope

- No `last_attempt_at` field without a consistent cross-worker heartbeat and
  staleness threshold.
- No automatic worker restart or replacement.
- No change to runtime health response schema.
- No readiness revocation for shutdown requested after the publication
  boundary.
- No change to cleanup aggregation or signal ownership.

## Completion Evidence

- Scheduled workers attempt configured periodic operations; the export worker
  also performs startup/requested reconciliation, idle queue polling, and
  per-job composition. A single `last_attempt_at` would not identify the same
  lifecycle event across these modes and cannot support a universal stale
  decision without an expected heartbeat interval.
- Before this change `require_all_running()` checked liveness but did not reject
  the shared shutdown event.
- A shutdown request may race with the five worker starts while all threads are
  still alive, allowing `daemon/started` immediately before cleanup.
- The supervisor already owns both the shutdown event and the authoritative
  readiness boundary, so it can reject this state without parallel ownership.
- `require_all_running()` now rejects an already-set shutdown event with
  `DaemonWorkerReadinessError` before inspecting worker liveness.
- Regression tests prove an alive worker cannot satisfy readiness after
  shutdown is requested, then exits cleanly through the normal join path.
- Process-lifecycle fixtures now model shutdown as a negative readiness
  condition, while request-driven shutdown remains a graceful post-readiness
  transition.
- Focused worker and daemon lifecycle tests: 59 passed.
- Full suite: 2165 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed.

## Publication

Shutdown-aware daemon readiness was implemented in `ce0db53`; milestone
publication is pending this goal update, push, and development-branch CI.

## Next Review Batch

After this boundary is complete, continue reviewing silent partial-success and
multi-step persistence paths.
