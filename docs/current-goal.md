# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Complete the shared agent failure policy's central classification of clear
implementation and process-integrity errors.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit Python exception families that must never become agent fallback.
2. Keep provider/runtime, validation, and availability failures recoverable.
3. Expand the shared non-recoverable classification.
4. Verify the policy directly and through chat/persona consumers.
5. Preserve original exception identity before and after tool execution.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Domain-specific explicitly typed catches remain unchanged.
- `RuntimeError`, `ValueError`, `OSError`, and unknown provider exception
  classes remain recoverable by the shared policy.
- Tool replay safety suppresses every subsequent model call, while the shared
  classification still decides between local fallback and propagation.

## Completion Evidence

- Shared policy rejects assertion, attribute, import, lookup, memory exhaustion,
  name resolution, unimplemented-path, recursion, syntax, system, and type
  errors.
- Direct tests cover both `KeyError` and `IndexError` through `LookupError`, and
  verify runtime, validation, operating-system, and unknown provider exception
  classes remain recoverable.
- Chat, persona graph, and discussion orchestration consume the expanded policy
  and preserve exact exception identity without fallback diagnostics.
- After a tool outcome, both recoverable and implementation failures suppress
  all further model calls; only the recoverable failure uses local fallback.
- Focused shared-policy and consumer tests: `87 passed`.
- `.venv/bin/pytest -q`: `1612 passed` with no warnings.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `54955de`.

## Next Review Batch

Continue auditing normal-result fallbacks after the central policy is complete.
