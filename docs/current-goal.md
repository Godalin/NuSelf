# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Represent active-log write, rollback, and close failures without losing
causality or hiding an uncertain persistence outcome.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit active data-handle write, rollback, and close precedence.
2. Specify close-time durability uncertainty and retry visibility.
3. Add one typed lifecycle error retaining every failed phase.
4. Preserve raw append errors when rollback and close both succeed.
5. Verify success-close and write-rollback-close failure combinations.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Per-record `fsync` remains disabled; successful close is process-visible, not
  crash-durable, completion.
- A close failure after complete write is an uncertain outcome and prevents
  observer delivery.
- The lifecycle error exposes exception objects, not event payload content.

## Completion Evidence

- `LogAppendLifecycleError` independently retains append, rollback, and close
  exceptions and chains the append error first when present.
- A complete write followed by close failure reports
  `record_may_have_persisted=True`, prevents observer delivery, and states the
  uncertain outcome in its stable error message.
- A partial write whose rollback and close both fail retains all three exact
  exception objects and reports the record as possibly persisted.
- A lone append failure with successful rollback and close remains the original
  exception, preserving the ordinary clean-failure contract.
- Focused log infrastructure tests: `59 passed`.
- `.venv/bin/pytest -q`: `1555 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `66c13f0`.

## Next Review Batch

Audit retry callers for uncertain log persistence outcomes.
