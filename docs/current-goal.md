# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Global and reason-thread personas now share one collection-based
repository protocol, and thread-local personas use scoped SQLite workspace
storage.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `PersonaPromptRepository` consumes one `StorageCollection`; its raw
  directory mode and derived name-index implementation are deleted.
- `WorkspaceCollection` adapts a namespaced `ScopedWorkspace` to the canonical
  collection protocol.
- Global persona composition roots inject the durable collection; reason
  persona tools inject the thread workspace collection.
- Reason service, workspace tools, and persona tools share the canonical
  `("workspace", "reason", thread_id)` namespace.
- Dynamic-persona and workspace specs describe the actual SQLite-backed
  implementation and explicitly reject migration of non-authoritative scratch
  JSON.
- Focused persona/workspace/reason tests: 68 passed.
- Final full tests: 1373 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing record-level legacy defaults after removing the larger
repository-level dual protocol.
