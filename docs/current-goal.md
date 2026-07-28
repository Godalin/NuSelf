# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Reject non-callable handler and event components at composition time.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit handler, middleware, subscriber, and validator registration.
2. Define fail-fast runtime callable contracts.
3. Validate constructor and incremental composition paths.
4. Preserve sealed/duplicate/name behavior and valid callable objects.
5. Verify invalid components fail before seal, dispatch, or publish.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Static typing remains the primary developer interface.
- Callable instances and bound methods remain valid components.
- Delivery-time subscriber exceptions remain independently aggregated.

## Completion Evidence

- `HandlerRegistry` rejects non-callable handlers and middleware during both
  construction and incremental composition, before sealing or dispatch.
- `EventPublisher` and `RuntimeEventDefinition` reject non-callable subscribers
  and payload validators before publication.
- Invalid handlers are not registered; existing duplicate, sealed, valid
  callable, and delivery-time failure behavior remains covered.
- Focused runtime composition suite: `44 passed`.
- Full test suite: `1620 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `cd8da8c`.

## Next Review Batch

Continue reviewing internal-message subscription and delivery lifecycle after
composition contracts fail fast.
