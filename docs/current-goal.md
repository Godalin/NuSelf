# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make Reflection relevance scoring and candidate generation consume the shared
typed Agent exception contract. Invocation failure and domain materialization
must use separate boundaries so arbitrary Agent implementation errors cannot
masquerade as valid conservative fallback.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory Reflection and Persona multi-exception fallback scopes.
2. Compare Reflection catches with the shared Agent error hierarchy.
3. Reproduce raw Agent `RuntimeError` and `ValueError` being converted into
   relevance or candidate fallback.
4. Specify invocation-versus-materialization classification.
5. Catch typed `AgentError` only around invocation and semantic `ValueError`
   only around Reflection domain conversion.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No change to relevance or candidate fallback result shapes.
- No change to Reflection audit event schemas.
- No retry inside the Reflection components.
- No compatibility for custom agents that violate the typed exception contract.
- Persona fallback boundaries remain the next independent review batch.

## Completion Evidence

- Reflection relevance scoring now catches `AgentError` only around invocation
  and catches semantic `ValueError` only while materializing `RelevanceScore`.
- Candidate generation uses the same split boundary for typed invocation and
  `IdeaCandidate` materialization.
- Shared structured agents already translate unavailable models, protocol
  failures, and invalid structured output into the `AgentError` hierarchy.
- Regression tests prove raw implementation `RuntimeError` and `ValueError`
  propagate with their original exception identity from both components.
- Both fallback paths are already observable through sealed Reflection audit
  events; no new event is required.
- Focused Reflection scheduler and audit tests: 80 passed.
- Full suite: 2151 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed; static search finds no remaining combined
  `(RuntimeError, ValueError)` catch in the Reflection scheduler.

## Publication

Typed Reflection Agent failure boundaries were implemented in `d1c7364`;
milestone publication is pending this goal update and push.

## Next Review Batch

After this boundary is complete, apply the same review to Persona selection,
scoring, moderator, and tool invocation fallbacks.
