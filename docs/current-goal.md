# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Bound durable-job wake-up admission independently of request volume while
preserving manifest authority. Pending and in-flight wake-ups must coalesce by
durable job identity, and capacity pressure must trigger online reconciliation
instead of blocking producers or losing work until restart.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory initial enqueue, retry timers, startup reconciliation, duplicate
   wake-ups, in-flight ownership, stop/drain, and manifest authority.
2. Update durable-job, Reason output, development, and hardcode specs first.
3. Add a shared bounded identity-deduplicating job admission queue.
4. Keep identity active through processing and release it explicitly afterward.
5. On capacity pressure, request online manifest reconciliation after capacity
   is released; preserve retry backoff ownership.
6. Prove duplicate, in-flight, full-capacity, recovery, and stop behavior.
7. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No persistent queue parallel to the manifest.
- No blocking producer/request threads on queue capacity.
- No early execution of jobs waiting on retry backoff timers.
- No change to deterministic job IDs, retry limits, or composition semantics.

## Completion Evidence

- Bounded identity-deduplicating job admission completed in `7f3a05b`.
- `JobAdmissionQueue` coalesces `(name, job_id, resource_id)` across pending and
  in-flight states and requires explicit completion.
- Reason export pending wake-ups are capped at 256 without blocking producers.
- Capacity pressure requests online manifest reconciliation after the worker
  releases capacity; a focused real-manifest test proves the omitted job is
  recovered in the same process.
- Live retry-timer identities are excluded from reconciliation, preserving
  backoff.
- Focused job contract, admission, output queue, and export recovery tests:
  61 passed.
- Full suite: 2092 passed.
- Pyright: 0 errors, 0 warnings.
- Static search proves production code no longer owns a `SimpleQueue` or raw
  `queue.Queue`; `git diff --check` passed.

## Publication

Bounded durable-job wake-up admission was implemented in `7f3a05b`; milestone
publication is pending this goal update and push.

## Next Review Batch

Review delayed retry scheduling next. Reason export still owns raw
`threading.Timer` instances, retains completed timers until another retry is
scheduled, and can strand its retry identity if timer start fails. Inventory
timer lifecycle, shutdown races, context retention, and failure observability,
then decide whether delayed wake-ups need a shared owned scheduler rather than
domain-managed timer lists.
