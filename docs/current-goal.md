# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — preserve complete provenance bodies internally and in email.

## Objective

Remove character-level abbreviation from the provenance query model and make
abbreviation an explicit presentation policy. Reflection Inbox/email must
render complete node bodies while retaining bounded graph traversal.

## Next Steps

1. Specify the query-versus-rendering ownership of abbreviation.
2. Preserve complete normalized bodies in every ProvenanceNode.
3. Render complete original and translated bodies in Reflection notifications.
4. Run focused/full validation and review the complete diff.
5. Merge a feature PR into `dev/v0.4.x` and return this file to Idle.

## Exclusions

- Do not remove node-count, traversal-depth, cycle, or deduplication bounds.
- Do not rewrite persisted Memory, Reflection, or ThoughtTrace records.
- Do not make the provenance query depend on email or another frontend.
- Do not expose hidden model reasoning.

## Completion Evidence

- ProvenanceService never truncates a node body by character count.
- Character abbreviation, when needed, is owned explicitly by a renderer.
- Reflection Inbox/plain email/HTML email preserve complete node bodies and
  translations with stable node ordering and blank-line separation.
- Long legacy Reflection traces still use the non-duplicating derivation
  projection introduced in PR #15.
- Pyright, focused tests, full suite, CI, and diff review pass.
