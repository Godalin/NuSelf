# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make event subscription changes during delivery deterministic and reentrant.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit subscription snapshots, cancellation, and callback reentrancy.
2. Define publication-boundary snapshot semantics.
3. Verify subscribe and unsubscribe mutations do not alter the active delivery.
4. Verify callbacks may publish recursively without holding the registry lock.
5. Preserve registration order, filtering, isolation, and failure aggregation.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Event delivery remains synchronous and in-process.
- Subscription mutations affect later and nested publications, not the active
  snapshot.
- Cross-process subscriptions continue to use the explicit activity transport.

## Completion Evidence

- The runtime specification defines one ordered subscription snapshot per
  publication and lock-free callback invocation.
- Tests prove cancellation cannot remove a subscriber from the active snapshot
  and subscription cannot add one to it.
- Tests prove a nested publication observes preceding subscription mutations
  and completes without publisher-lock deadlock.
- Existing registration order, name filtering, and publisher-lifetime behavior
  remains covered.
- Focused runtime event suite: `22 passed`.
- Full test suite: `1622 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `e1c577a`.

## Next Review Batch

Continue reviewing event-delivery ownership and failure boundaries after
subscription snapshot semantics are explicit.
