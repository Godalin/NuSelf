# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make Persona discussion stages and `persona_think` tools consume the shared
typed Agent exception contract. Arbitrary Agent implementation errors must not
masquerade as neutral discussion output, deterministic host fallback, or a
normal sanitized tool failure.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory Persona discussion and tool multi-exception fallback scopes.
2. Compare scoring, selection, moderator, and text-tool catches with the shared
   Agent error hierarchy.
3. Reproduce raw Agent `RuntimeError` and `ValueError` being converted into
   normal Persona fallback.
4. Specify the recoverable typed invocation contract.
5. Catch `AgentError` only at each Agent invocation boundary.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No change to Persona fallback result or tool error-string shapes.
- No change to Persona audit event schemas.
- No retry inside Persona discussion or tools.
- No compatibility for custom agents that violate the typed exception contract.
- No changes to graph activation, contribution, or synthesis boundaries that
  already use shared failure classification.

## Completion Evidence

- Persona scoring, participant selection, and moderator judgment now catch only
  `AgentError` around structured Agent invocation.
- Global and reason-thread `persona_think` tools likewise render sanitized
  errors only for typed `AgentError`.
- Shared structured and free-text agents already translate recoverable model,
  protocol, and invalid-output failures into the `AgentError` hierarchy.
- Regression tests prove raw implementation `RuntimeError` and `ValueError`
  propagate with their original exception identity across all five boundaries.
- Existing Persona audit events already observe legitimate typed discussion
  degradation; no new event is required.
- Focused Persona discussion, tool, and audit tests: 64 passed.
- Full suite: 2161 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed; static search finds no remaining combined
  `(RuntimeError, ValueError)` catch in Persona discussion or tools.

## Publication

Typed Persona Agent failure boundaries were implemented in `f738a34`;
milestone publication is pending this goal update and push.

## Next Review Batch

After this boundary is complete, continue into worker failure propagation,
health, and recovery semantics.
