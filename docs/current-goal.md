# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Share one sealed definition registry without conflating event transports.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Compare runtime event and persisted audit ownership/failure semantics.
2. Extract generic duplicate-safe, resolvable, sealable registry mechanics.
3. Rebuild `EventDefinitionRegistry` as a semantic adapter over that primitive.
4. Move lifecycle audit definitions from a mapping proxy to the same primitive.
5. Preserve separate definition types, extension policy, and delivery paths.
6. Verify duplicates, unknown keys, late registration, ordering, and isolation.
7. Run full quality gates, commit, and push.

## Out Of Scope

- Runtime events remain synchronous immutable envelope delivery.
- Lifecycle audits remain direct best-effort persisted projections.
- No audit replay, implicit event publication, or shared extension namespace.

## Completion Evidence

- The review established that runtime events and lifecycle audits have distinct
  delivery, extension, failure, and replay semantics and must not be merged.
- `runtime.definitions.DefinitionRegistry` now owns ordered registration,
  duplicate rejection, lookup, explicit sealing, and immutable snapshots.
- The generic registry accepts any hashable key and definition value, including
  `None`; unknown lookup does not rely on a sentinel definition value.
- `EventDefinitionRegistry` is now a semantic adapter over the shared primitive
  and preserves its public producer/name API and event-specific exceptions.
- Core plus domain runtime-event composition still rejects duplicates and late
  mutation and validates unknown events before synchronous delivery.
- The daemon lifecycle audit registry now uses the same primitive with
  event-slug keys while retaining its closed definition type and exact schemas.
- Audit registration remains sealed at module composition; runtime event
  domains retain their explicit extension path.
- No audit write publishes an envelope, no runtime publication implicitly
  writes a lifecycle audit, and persisted records remain non-replayable.
- Direct tests cover generic ordering, lookup, snapshots, duplicates, sealing,
  unknown keys, invalid composition, nullable definitions, event adapters, and
  audit registry immutability.
- Focused definition/event/observability/audit suites: `65 passed`.
- Full test suite: `1750 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is ready to publish through implementation commit `d2424c1`.

## Next Review Batch

Review runtime event and audit naming/versioning policy after registry mechanics
have one owner.
