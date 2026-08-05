# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle — no active implementation goal.

## Objective

No active objective.

## Next Steps

1. Wait for the next explicitly approved goal.

## Exclusions

- Do not begin unapproved feature or refactor work.

## Last Verification

- Daemon Chat returns typed approval challenges; CLI/REPL decisions are bound
  to the exact request and replay the same uncommitted turn.
- Missing approval infrastructure is distinct from an actual user decline, and
  approval pauses are not logged as failed Tool calls or turns.
- Chat exposes read-only `runtime_time` with local timezone and UTC timestamps.
- `uv run --locked pytest`: 2,344 passed.
- `uvx pyright`: 0 errors, 0 warnings.
- `git diff --check`: passed.
