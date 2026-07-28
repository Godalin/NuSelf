# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The chat tool-safe retry boundary is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

None until the next review batch begins.

## Out Of Scope

None while idle.

## Completion Evidence

- Chat supervisor middleware exposes invocation-local tool outcomes.
- Any successful or failed tool outcome suppresses same-endpoint retry and
  cross-endpoint failover for that turn.
- Suppression writes `chat/llm_retry_suppressed_after_tool_call` and uses the
  existing no-tool fallback without replaying tools.
- Failures before the first tool preserve bounded retry and failover.
- `.venv/bin/pytest -q`: `1474 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `a3dc758`.

## Next Review Batch

Audit reason advancer endpoint availability without permitting tool replay.
