# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The reason advancer tool-safe failover migration is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

None until the next review batch begins.

## Out Of Scope

None while idle.

## Completion Evidence

- `ReasonAdvancer` builds one equivalent tool-enabled agent per configured
  endpoint.
- Availability failures before tool execution use the shared endpoint
  failover primitive and persist endpoint success.
- Non-availability errors do not fail over.
- Any typed tool outcome suppresses endpoint switching and raises a chained
  `ReasonAdvanceError` after projecting tool evidence.
- `.venv/bin/pytest -q`: `1479 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `75c397c`.

## Next Review Batch

Audit remaining legacy chat response fallback and LLM adapter boundaries.
