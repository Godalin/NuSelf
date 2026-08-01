# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle — no active implementation goal.

## Last Completed Goal

Closed the scheduler and feature-policy correctness gaps identified by the
external daemon architecture review without adding a service bus, scheduler,
or lock hierarchy.

## Completion Evidence

- Capacity saturation and busy resource lanes now put the dispatcher to sleep
  until a relevant notification instead of using zero-timeout waits.
- Chat fails closed when scheduling is unavailable. After durable turn and
  observation commit, curation/compression admission is recoverable wake-up;
  periodic scans rediscover both forms of maintenance.
- `@observed` centrally emits payload-safe feature started/completed/failed
  events through the normal log/activity projection.
- Scheduler health exposes only current task kind/error type degradation and
  clears it after a successful task; production task construction uses the
  closed typed kind boundary.
- `uv run --locked pytest -q`: 2450 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- `uv build`: sdist and wheel built successfully.
- Python 3.12 clean-wheel install, imports, and `nuself --version` succeeded.
