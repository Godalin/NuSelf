# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close shared storage cleanup audit ownership so backend close and CLI cleanup
failure use one exact validated contract without losing aggregated errors.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory default backend close and CLI cleanup failure producers,
   aggregation, exception identity, metadata, and consumers.
2. Decide one storage-owned contract that preserves every cleanup error
   without duplicating primary exception text.
3. Update storage, error, log, and development specs before implementation.
4. Define one sealed storage operations audit registry with fixed messages and
   exact per-event metadata.
5. Route storage reset and CLI lifecycle cleanup through the shared adapter
   without changing close attempts, aggregation, or raised exceptions.
6. Remove raw storage/CLI `report_observed_failure` calls, lossy step-only
   metadata, and compatibility aliases.
7. Run focused and full quality gates, commit by functional boundary, and
   push.

## Out Of Scope

- No change to backend selection or process-global backend ownership.
- No change to close/reset ordering or attempt count.
- No change to `DefaultBackendResetError` or `CliLifecycleError` propagation.
- No change to daemon cleanup contracts.

## Completion Evidence

- Daemon operations audit ownership completed in `3b00e68`.
- Worker join timeout and daemon cleanup failure now use one sealed operations
  registry.
- Cleanup diagnostics preserve ordered `{step,error}` records; timeout
  metadata no longer duplicates `status="timed_out"`.
- Server/worker owners no longer construct operational audit presentation.
- Initial next-batch inspection finds raw storage events for
  `backend_close_failed` and CLI `cli_cleanup_failed`; the latter currently
  retains only step names rather than nested errors.
- Focused tests: 58 passed.
- Full suite: 2035 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Daemon operations audit ownership was implemented in `3b00e68`; milestone
publication is pending this goal update and push.

## Next Review Batch

Continue shared handler/log/message infrastructure review after storage
cleanup audit ownership is verified and published.
