# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make memory curator and optimizer consume the shared typed Agent exception
contract. Agent invocation failure and domain action materialization failure
must use separate boundaries so arbitrary implementation errors cannot
masquerade as a valid deferred decision.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory multi-exception fallback scopes.
2. Compare memory decision catches with the shared Agent error hierarchy.
3. Reproduce raw agent `RuntimeError` and `ValueError` being deferred.
4. Specify invocation-versus-materialization classification.
5. Catch typed `AgentError` only around invocation and semantic `ValueError`
   only around domain conversion.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No change to deferred result shape or existing deferred audit events.
- No change to action validation rules.
- No retry inside curator or optimizer.
- No compatibility for custom agents that violate the typed exception contract.

## Completion Evidence

- Shared structured agents raise `AgentModelUnavailableError`,
  `AgentProtocolError`, or `AgentInvalidOutputError`, all under `AgentError`.
- Curator and optimizer now catch `AgentError` only around `agent.invoke(...)`;
  legitimate typed invocation failures still produce the existing deferred
  result and structured audit.
- Action materialization has a separate semantic `ValueError` boundary, so
  invalid domain actions still defer without conflating invocation failures.
- Regression tests prove raw implementation `RuntimeError` and `ValueError`
  propagate with their original exception identity.
- Curator and optimizer already write structured deferred audit events after a
  legitimate deferred decision; no new fallback event is required.
- Focused curator and optimizer tests: 49 passed.
- Full suite: 2147 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed; static search finds no remaining combined
  `(RuntimeError, ValueError)` catch in either memory decision path.

## Publication

Typed memory Agent failure boundaries were implemented in `336b6c2`;
milestone publication is pending this goal update and push.

## Next Review Batch

After this boundary is complete, inspect reflection and persona multi-error
fallbacks for the same invocation/materialization scope ambiguity.
