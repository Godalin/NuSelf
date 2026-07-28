# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. `relations` is now the only memory/profile relation wire schema; obsolete
relation fields are rejected instead of read or written.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Memory entries, candidates, profile items, and `MemoryObject` payloads write
  only the `relations` object.
- Entry, candidate, and profile decoders require `relations` and reject
  `supersedes` / `related_memory_ids` even when canonical data is also present.
- Memory-object validation rejects obsolete relation payload fields.
- `source_refs`, notification-context upgrade reads, and historical log reads
  remain because their migration contracts are explicit.
- The full suite exposed and now covers concurrent SQLite dynamic-column
  expansion across separate backend connections.
- Focused memory/profile tests: 68 passed.
- SQLite concurrency stress test: 5 consecutive passes.
- Final full tests: 1381 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Require `terminal_status` in persisted reason steps instead of silently
defaulting missing records to `continue`.
