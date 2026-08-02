# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle — detailed-default tool logs and explicit compact output complete.

## Objective

Make observed tool outcomes include structured arguments and result/error by
default. Add one orthogonal `@compact` declaration for tools that intentionally
need operation/status-only activity, without duplicating outcome events.

## Next Steps

None.

## Exclusions

- Do not log `feature.started/completed/failed` function arguments or raw
  exception messages; those lifecycle events remain payload-safe.
- Do not add a logging base class, mode registry, or second tool-outcome path.
- Do not change tool return values or user-visible tool behavior.

## Last Verification

- Observed tool activity now includes structured `args` plus `result` or
  `error` by default and renders through the shared tool-I/O renderer.
- `@compact` is an independent inert policy that intentionally retains only
  component, operation, and status; it does not change execution or results.
- Payload-safe `feature.started/completed/failed` events remain free of tool
  arguments, results, and raw exception messages.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- Default `uv run pytest -q`: 2390 passed.
- `uv build`: sdist and wheel succeeded.
