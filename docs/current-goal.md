# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — ordered cross-domain provenance chains.

## Objective

Build one service-owned, bounded provenance-chain query from Conversation or
Reason evidence through Trace and Memory into Reflection, then render that
ordered chain at the end of Reflection notifications.

## Next Steps

1. Specify chain nodes, ordering, traversal limits, and service boundaries.
2. Implement cycle-safe Trace traversal and service-only artifact summaries.
3. Inject the chain query into Reflection notification composition.
4. Add focused and full validation plus user documentation.
5. Review and merge a feature PR into `dev/v0.4.x`.

## Exclusions

- Do not expose repositories across package boundaries.
- Do not include hidden model reasoning or raw persona discussion traces.
- Do not fabricate content for missing, compacted, or deleted artifacts.
- Do not let provenance rendering failure roll back a persisted Reflection.

## Completion Evidence

- Chat-origin chains order conversation turn, relevant ThoughtTrace records,
  memory, Reflection trace, and Reflection artifact.
- Reason-origin chains replace the conversation turn with the Reason step and
  its trace while retaining the same downstream ordering.
- Traversal is deterministic, deduplicated, cycle-safe, and bounded.
- Artifact summaries resolve through public services only; tombstones remain
  explicit.
- Reflection Inbox and HTML/plain email render the same ordered chain.
- Pyright, focused tests, full suite, CI, and diff review pass.
