# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. `ConversationGraphRuntime` is now the sole conversation runtime class
name, with no `ChatAgent` compatibility alias or daemon composition field.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- The compatibility assignment and package-root export are deleted.
- Production CLI, daemon, evaluation, request-state protocols, and tests import
  `ConversationGraphRuntime` directly.
- Daemon composition owns `conversation_runtime`; no `chat_agent` state field
  remains.
- Graph node methods remain explicit testable seams and are no longer
  documented as compatibility adapters.
- `rg '\bChatAgent\b' src tests` returns no code or test references.
- Focused chat, graph, daemon, CLI, and evaluation tests: 399 passed.
- Final full tests: 1387 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit the local chat response compatibility parser and remaining legacy
persisted-data fallbacks, separating removable parallel runtime protocols from
explicit storage migrations.
