# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Converge chat response retry/failover on the shared agent endpoint runner while
preserving tool-safe replay suppression and deterministic local fallback.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Specify shared same-endpoint retry and endpoint-switch policy.
2. Extend the shared endpoint runner with bounded retry hooks.
3. Migrate chat response off its private endpoint loop.
4. Preserve immediate suppression after any tool outcome.
5. Verify protocol errors retry once but never switch endpoints.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep chat's deterministic local response after exhausted or unsafe model
  execution.
- Keep supervisor construction in chat because it owns chat tools and
  middleware.

## Completion Evidence

- `ConversationResponseSynthesizer` delegates endpoint ordering, success
  preference, availability classification, and failover diagnostics to
  `invoke_agent_endpoint`.
- The shared runner supports validated bounded same-endpoint attempts, a retry
  predicate, a failover predicate, and a retry observer.
- Chat protocol failures retry endpoint 0 once and do not invoke endpoint 1.
- Chat availability failures switch from endpoint 0 to endpoint 1.
- Any captured tool outcome closes both predicates before another invocation
  and enters the deterministic local response.
- `.venv/bin/pytest -q`: `1468 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `627123d`.

## Next Review Batch

Audit whether chat's tool-enabled supervisor can reuse more of the structured
agent construction without hiding middleware state.
