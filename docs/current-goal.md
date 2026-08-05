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

- Chat exposes `memory_create` for durable preferences, beliefs, goals,
  episodes, and facts found in the current conversation.
- The Tool creates one draft Memory entry through `MemoryService` only after an
  affirmative `ApprovalPort` decision.
- Rejection performs no write and returns an explicit Tool result to the Agent;
  Memory Skill policy requires a no-save response without automatic retry.
- `uv run --locked pytest`: 2,338 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- `git diff --check`: passed.
