# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Daemon worker lifecycle is now a production-owned `EventPublisher`
boundary with audit logs as an explicit subscriber.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `DaemonState` owns one `EventPublisher`, attaches
  `runtime_event_log_sink(...)`, and injects it into the worker supervisor.
- Every worker target publishes registered `worker.started` and
  `worker.stopped` envelopes; scheduled and escaping failures publish
  `worker.failed` with the domain operation event retained in metadata.
- Successful audit projections retain the event envelope ID and worker/job
  runtime context.
- A production-composition regression subscribes to `DaemonState`'s publisher
  and proves the start/stop audit records retain those exact envelope IDs.
- A regression test proves another subscriber may fail on both start and stop
  without skipping the target or stopped-event audit projection.
- Worker health, scheduled retry intervals, registration, export initialization,
  and join-timeout behavior remain unchanged.
- Focused runtime-event/worker/daemon/export tests: 66 passed.
- Final full tests: 1275 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit chat lifecycle event adoption after daemon worker lifecycle is real.
