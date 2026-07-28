# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Prevent chat's no-tool local fallback from hiding implementation errors before
any tool has executed.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Classify chat runtime broad catches by control-boundary ownership.
2. Define recoverable model/protocol failures versus programming errors.
3. Disable retry, failover, and local fallback for pre-tool programming errors.
4. Preserve local fallback after any tool outcome so tools are never replayed.
5. Verify attempt counts, exception identity, and tool-safe fallback.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Protocol/validation failures retain one bounded same-endpoint retry and local
  fallback.
- Availability failures retain ordered endpoint failover.
- Once a tool outcome exists, every `Exception` remains non-retryable and uses
  local fallback to avoid replay.

## Completion Evidence

- Pre-tool `AssertionError`, `AttributeError`, and `TypeError` failures are
  ineligible for same-endpoint retry, endpoint failover, and local fallback.
- Tests verify each implementation error is raised as the exact original
  object after one endpoint invocation and without an exhaustion diagnostic.
- Protocol validation retains one same-endpoint retry plus local fallback, and
  availability failure retains ordered endpoint failover.
- Once a tool outcome exists, an injected `AssertionError` still suppresses
  every further model call and enters the no-tool local fallback.
- Focused chat response/agent/failover tests: `101 passed`.
- `.venv/bin/pytest -q`: `1570 passed` with no warnings.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `54ac139`.

## Next Review Batch

Continue classifying broad domain catches after the chat fallback boundary is
explicit.
