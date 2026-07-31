# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — implementing the approved v0.3.1 unified daemon scheduler.

## Objective

Replace the daemon's scattered worker-specific wake-up, timer, queue, and lock
machinery with one small typed task-admission and dispatch model while keeping
one operating-system daemon process, responsive chat/control requests, durable
domain recovery, and bounded shutdown.

## Ordered Steps

1. [done] Specify the task envelope, stable identity, admission, scheduling,
   resource serialization, recovery, and shutdown contracts.
2. [done] Move chat, memory, reflection, reason, notification, and export onto
   one scheduler and one bounded executor.
3. [done] Remove worker supervisors, dedicated admission queues, delayed timer
   schedulers, worker health payloads, and export-worker lifecycle.
4. [done] Update governing runtime, error, development, reason-output, and
   architecture documentation.
5. [in progress] Run full release gates, commit the completed migration, push,
   and verify final CI.

## Exclusions

- Runtime events and audit logs remain observation only, never command input.
- Storage/repository transaction locks and the single-daemon instance lock.
- Multiple operating-system daemon processes or an unbounded executor pool.
- Distributed execution or a general-purpose message-bus framework.

## Completion Evidence

- Approved written design with explicit invariants and deletion targets.
- One typed scheduler replaces worker-specific in-memory coordination.
- Same-resource operations cannot overlap; unrelated bounded work may proceed.
- Shutdown, recovery, queue saturation, and duplicate admission are tested.
- Net daemon infrastructure is smaller and the full gate is green.
