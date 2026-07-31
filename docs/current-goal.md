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

1. Specify the minimal task envelope, stable identity, admission, scheduling,
   resource-serialization, recovery, and shutdown contracts.
2. Map each current daemon responsibility to the proposed model and identify
   which locks and worker abstractions disappear.
3. Record the approved governing design and migration sequence.
4. Update authoritative daemon/runtime specifications before implementation.
5. Implement in reversible commits with focused concurrency and recovery
   tests, then run full release gates and final CI.

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
