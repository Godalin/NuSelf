# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Replace daemon reads of private chat runtime fields with an immutable,
explicit agent capability snapshot.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Specify snapshot ownership and immutability.
2. Add a shared capability value for endpoints and readonly tools.
3. Expose a public snapshot method on the conversation runtime.
4. Migrate daemon scheduler startup off `_tools` and `_langchain_models`.
5. Verify registry mutation cannot change an existing snapshot.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep tool/model objects shared by identity; copy only the containing
  collections.
- Keep chat's internal mutable registry private.

## Completion Evidence

- `AgentCapabilitySnapshot` is a frozen value containing endpoint and readonly
  tool tuples.
- `ConversationGraphRuntime.capability_snapshot()` owns readonly-tag
  filtering and copies collection membership.
- Clearing the runtime tool registry after snapshot creation does not alter
  the issued snapshot.
- Daemon reason scheduler startup consumes only the public snapshot and works
  with a runtime exposing no private tool/model fields.
- Production search finds no daemon access to `_tools` or
  `_langchain_models`.
- `.venv/bin/pytest -q`: `1468 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `a55d750`.

## Next Review Batch

Audit remaining `getattr`/private-field composition across daemon worker
startup.
