# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Use one shared agent failure policy so persona fallbacks do not hide clear
implementation errors.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit persona activation, contribution, and synthesis fallback boundaries.
2. Promote chat's failure eligibility rule into shared agent infrastructure.
3. Preserve runtime/protocol/validation fallback behavior.
4. Propagate assertion, attribute, and type errors from persona nodes.
5. Verify all three persona stages and the existing chat policy.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Competitive discussion owns separate fallback policy and remains unchanged.
- Provider/runtime and structured-validation failures retain deterministic
  persona fallbacks.
- Diagnostic persistence remains secondary to a legitimate fallback.

## Completion Evidence

- `is_recoverable_agent_failure(...)` in shared agent infrastructure owns the
  assertion/attribute/type classification previously private to chat.
- Chat retry, failover, and local fallback consume that shared policy without
  changing their verified tool-replay behavior.
- Persona activation, contribution, and synthesis propagate each classified
  implementation error as the exact original object and write no fallback
  diagnostic.
- Existing `RuntimeError` provider failures and structured validation failures
  retain their deterministic persona fallbacks.
- Focused persona, chat-response, and structured-agent tests: `52 passed`.
- `.venv/bin/pytest -q`: `1583 passed` with no warnings.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `133e7f8`.

## Next Review Batch

Continue classifying fallback boundaries after shared agent failure ownership
is established.
