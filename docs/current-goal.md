# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — stable identities and replay semantics for non-idempotent agent tools.

## Objective

Make reflection mutations and Reason thread creation/export safe across
approval delays and repeated delivery by resolving durable resource identities
before mutation and enforcing domain-owned replay semantics.

## Next Steps

1. Specify stable resource references, operation keys, replay results, and
   conflict behavior at the service boundary.
2. Replace reflection mutation indexes with durable entry identifiers.
3. Add domain-owned idempotency for Reason thread creation and make export
   planning replay-safe without deleting existing artifacts.
4. Cover same-key replay, conflicting reuse, approval-delay list changes, and
   failure/retry behavior with focused tests.
5. Run the full test, type-check, build, and diff validation suite; review and
   merge through a short-lived PR.

## Exclusions

- Persistent LangGraph checkpointing or transport-level exactly-once claims.
- A generic distributed transaction coordinator across domain stores.
- Retrofitting every existing low-risk mutation in this change.

## Completion Evidence

- Reflection agent mutations accept stable entry IDs rather than shifting
  numeric handles.
- Repeating a Reason creation/export operation with the same key and payload
  returns the original durable result without duplicating or resetting work.
- Reusing one key with different semantic input fails explicitly.
- Focused and full tests, Pyright, package builds, and CI pass.
