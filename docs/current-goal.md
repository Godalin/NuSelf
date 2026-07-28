# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The typed tool-outcome migration is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

None until the next review batch begins.

## Out Of Scope

None while idle.

## Completion Evidence

- Shared middleware emits immutable `ToolOutcome` records with detached
  arguments and exactly one of result or error.
- Chat retry suppression consumes typed outcomes without positional tuples.
- Reason tool-log projection preserves result/error status in the existing
  public wire shape.
- Tool outcomes are projected before a later reason-agent failure propagates;
  projection failure cannot replace the agent error.
- `.venv/bin/pytest -q`: `1477 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `1f8f661`.

## Next Review Batch

Add tool-safe reason endpoint failover using typed outcomes.
