# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — separate Reflection artifacts from producer Trace semantics.

## Objective

Remove duplicated Reflection prose from provenance by making the artifact own
its title/body and its producer ThoughtTrace own only derivation facts and
public decisions. Keep structured evidence references out of user prose.

## Next Steps

1. Specify artifact, producer Trace, and evidence-reference responsibilities.
2. Render old and new Reflection traces as derivation summaries.
3. Prevent candidate prose from repeating structured artifact references.
4. Run focused/full validation and review the complete diff.
5. Merge a feature PR into `dev/v0.4.x` and return this file to Idle.

## Exclusions

- Do not remove producer Trace nodes from the provenance chain.
- Do not rewrite existing persisted Reflection or ThoughtTrace records.
- Do not expose hidden model reasoning or discussion transcripts.
- Do not infer evidence references from prose.

## Completion Evidence

- Reflection artifact nodes remain the only provenance nodes that display the
  final title/body.
- Reflection producer Trace nodes display type, evidence count, score,
  discussion disposition, and bounded public decisions without final prose.
- Existing traces recorded with `summary=body` render through the new semantic
  projection without data migration.
- New candidate title/body text excludes bracketed artifact references while
  `evidence_refs` retains the validated canonical references.
- Pyright, focused tests, full suite, CI, and diff review pass.
