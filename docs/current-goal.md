# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — adding approval-gated conversational memory creation.

## Objective

Let the Chat Agent propose and create a draft durable memory during the current
conversation, but execute the write only after explicit frontend approval and
return a clear no-write Tool result after rejection.

## Next Steps

1. Completed: specified Tool input, draft persistence, and approval results.
2. Completed: implemented `memory_create` through the decorated boundary.
3. Completed: tested approval, declined no-op, and Agent-visible refusal.
4. In progress: commit the verified implementation and return this file to
   Idle.

## Exclusions

- Do not bypass `MemoryService` or write directly to a Repository.
- Do not treat conversational creation as curator auto-acceptance or create a
  reviewed memory without a separate policy decision.
- Do not change confirmation requirements of existing Memory mutation Tools.

## Completion Evidence

- Chat's Tool registry includes `memory_create` as a write Tool with required
  confirmation metadata.
- Approval creates exactly one draft Memory entry through `MemoryService`.
- Rejection creates no entry and returns an explicit Tool result visible to the
  Agent loop.
- Memory Skill explains when to propose creation and how to handle rejection.
- `uv run --locked pytest`: 2,338 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- `git diff --check`: passed.
