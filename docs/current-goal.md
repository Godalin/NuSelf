# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Reduce structured-log sync overhead without weakening per-record durability.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit whether batching can preserve the synchronous append/observer contract.
2. Keep every record as an independently acknowledged durable transaction.
3. Identify redundant directory synchronization without assuming path stability.
4. Cache only successfully synced active file identities with a strict bound.
5. Invalidate naturally on rotation or cross-process active-file replacement.
6. Verify repeat writes, identity changes, sync failure, and cache capacity.
7. Run full quality gates, commit, and push.

## Out Of Scope

- No asynchronous worker, flush timer, or group-commit queue is introduced.
- Data-file `fsync`, close, rollback, and observer ordering remain unchanged.
- Cache state is a process-local optimization, never persisted truth.

## Completion Evidence

- Implicit asynchronous batching was rejected because it cannot preserve the
  synchronous per-record append, close, error, and observer contract.
- A process-local LRU cache records only successfully directory-synced active
  `(device, inode)` identities and is capped at 256 paths.
- Consecutive appends to one unchanged active inode reuse its directory sync
  while every record still performs its own data-file `fsync`.
- First use, rotation/active identity replacement, retry after directory-sync
  failure, and safe cache eviction all trigger directory synchronization.
- Cache access is separately locked and remains an optimization; eviction or
  process restart can only add a redundant safe sync.
- Focused logging and observability suites: `89 passed`.
- Full test suite: `1668 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is ready for publication through `d66ffeb`.

## Next Review Batch

Review daemon raw-stream retention after structured-log synchronization no
longer repeats unchanged directory work.
