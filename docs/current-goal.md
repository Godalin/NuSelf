# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make runtime event subscriptions use the same complete `(producer, name)`
identity as registration and publication. Partial name-only selectors must not
cross subsystem boundaries when extensions register the same event name.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory definitions, same-named extension events, and every subscriber.
2. Update runtime-infrastructure, logging, and development contracts first.
3. Make subscriptions either unfiltered or exact `(producer, name)` selectors.
4. Reject partial and unregistered selectors at subscription composition time.
5. Prove same-named events from another producer cannot reach the subscriber.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No wildcard-by-producer or wildcard-by-name selectors.
- No change to event definition, envelope, payload, or delivery-failure shapes.
- No asynchronous delivery or subscriber retry.
- No compatibility support for name-only subscriptions.

## Completion Evidence

- Complete event subscription identity completed in `8765c8b`.
- Filtered subscriptions require both producer and name and resolve the sealed
  definition during composition.
- Partial and unknown selectors fail before a subscription is installed.
- A registered same-name extension event from another producer is proven not
  to reach the exact subscriber.
- Production subscribers contain no name-only selector.
- Focused runtime event, observability, daemon-worker, Chat, and daemon-server
  tests: 168 passed.
- Full suite: 2086 passed.
- Pyright: 0 errors, 0 warnings.
- Static subscription search and `git diff --check`: passed.

## Publication

Complete event subscription identity was implemented in `8765c8b`; milestone
publication is pending this goal update and push.

## Next Review Batch

Review durable job admission and backpressure next. The Reason export worker
uses an unbounded `SimpleQueue` while manifests are already authoritative;
inventory duplicate enqueue paths, restart reconciliation, cancellation, and
queue wake-up semantics, then determine whether the in-memory transport should
be bounded and identity-deduplicated rather than able to grow independently of
durable state.
