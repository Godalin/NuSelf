# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The persisted Memory read-model ownership batch is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `MemoryEntry`, `MemoryCandidate`, and `MemoryObject` detach and recursively
  freeze tags, source refs, relations, payload, metadata, and evidence
  membership.
- `to_wire()` returns detached standard list/dict containers without changing
  persisted fields.
- Descriptor validation, merge, graph projection, queries, conversions,
  curator, and optimizer operate on immutable collection abstractions.
- Focused Memory and integration tests: 103 passed.
- Full tests: 1234 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit remaining repository summary/index read models and source-domain records.
