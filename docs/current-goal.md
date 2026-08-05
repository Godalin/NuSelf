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

1. Specify the Tool input, draft persistence, and approval-result contract.
2. Implement `memory_create` through the decorated feature boundary.
3. Test approved creation, declined no-op behavior, and Agent-visible refusal.
4. Run full verification, commit in stages, and return this file to Idle.

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
- Relevant tests, full pytest, Pyright, and `git diff --check` pass.
