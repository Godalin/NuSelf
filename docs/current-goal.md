# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Move delayed retry lifecycle into shared owned scheduling. Timer start,
execution, completion, and cancellation must update ownership atomically so
completed timers do not linger and failed starts cannot strand durable jobs.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory all raw timers, completed-task retention, start failure, callback
   ownership, daemon shutdown races, and retry observability.
2. Update runtime-infrastructure, Reason output, error, and development specs.
3. Add a shared keyed delayed-task scheduler with atomic start rollback.
4. Remove ownership before callback execution and cancel all owned timers
   exactly once on close.
5. Migrate Reason retries; report schedule failure and request durable
   reconciliation without leaving a phantom retry identity.
6. Prove execution cleanup, start rollback, duplicate suppression, and close
   races.
7. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No persistent delayed-task store.
- No change to retry counts or exponential backoff values.
- No generic retry policy inside the scheduler.
- No compatibility retention of domain-owned timer lists.

## Completion Evidence

- Shared delayed scheduling completed in `ccb44e5`.
- `DelayedTaskScheduler` owns unique task keys, daemon timers, atomic start
  rollback, completion removal, and idempotent close/cancellation.
- Completed callbacks observe zero pending ownership; duplicate and post-close
  schedules do not create timers.
- Timer start failure removes and cancels the timer before propagating.
- Reason retry scheduling uses the shared owner; schedule failure emits sealed
  `daemon/export_retry_schedule_failed`, retains exact attempts/backoff
  metadata, and requests manifest reconciliation without a phantom retry key.
- Focused scheduler, Reason retry, export recovery, and audit tests: 115 passed.
- Full suite: 2098 passed.
- Pyright: 0 errors, 0 warnings.
- Static search proves `threading.Timer` exists only inside the shared scheduler;
  `git diff --check` passed.

## Publication

Shared delayed scheduling was implemented in `ccb44e5`; milestone publication
is pending this goal update and push.

## Next Review Batch

Review synchronous event subscriber latency ownership next. `EventPublisher`
isolates raised exceptions but invokes every subscriber inline with no
latency/timeout contract, so a blocked auxiliary subscriber can still block the
producer indefinitely. Inventory production subscriber effects and ordering
requirements before deciding whether log projection remains authoritative
inline work or needs an owned bounded delivery facility.
