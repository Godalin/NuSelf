# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make synchronous runtime-event latency ownership explicit. Preserve ordered
log projection before publication returns, while removing the misleading
general subscriber API that allowed arbitrary slow auxiliary effects to block
producers without declaring that ownership.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory production event subscribers and publish-return ordering
   dependencies.
2. Decide whether log persistence remains synchronous and whether any
   production auxiliary subscriber requires independent delivery.
3. Update runtime-infrastructure, logging, and development specs before code.
4. Replace the general subscriber API with explicit synchronous projection
   attachment and migrate every caller.
5. Prove ordering, snapshot mutation, failure isolation, and publisher-scoped
   detachment semantics under the new API.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No asynchronous event bus or background projection worker without a concrete
  independently progressing production consumer.
- No timeout implemented by abandoning callback threads.
- No compatibility alias for `subscribe()` or `unsubscribe()`.
- No change to event identities, payloads, ordering, or failure isolation.

## Completion Evidence

- Production inventory: daemon and standalone chat attach only
  `runtime_event_log_sink(...)`; no independently progressing production
  projection exists.
- Chat tests require completed events to observe already-persisted thread state,
  and event tests require ordered synchronous snapshot delivery.
- Runtime events now expose `attach_projection(...)` and
  `detach_projection(...)`; the old general `subscribe()` / `unsubscribe()`
  surface and `EventSubscriber` / `EventSubscription` types were removed
  without compatibility aliases.
- Specs require every attached projection to be bounded synchronous in-process
  work. Network calls, retries, unbounded waits, and independently progressing
  effects must instead own bounded queue and worker lifecycles.
- Daemon, standalone chat, tests, exports, error details, and exact-identity
  filtering use the new projection vocabulary and handles.
- Focused event, observability, chat, daemon worker, and daemon server tests:
  168 passed.
- Full suite: 2098 passed.
- Pyright: 0 errors, 0 warnings.
- Static search found no old event subscription API or type references;
  `git diff --check` passed.

## Publication

Synchronous projection ownership was implemented in `1181f90`; milestone
publication is pending this goal update and push.

## Next Review Batch

Review ad hoc thread ownership next. The runtime now centralizes long-lived
workers and delayed callbacks, but interactive activity still creates a raw
per-turn `threading.Thread` for the blocking daemon chat request. Verify
start-failure rollback, exception handoff, cancellation, final join, and whether
the one-shot thread belongs in shared owned execution infrastructure.
