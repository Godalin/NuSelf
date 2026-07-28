# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make shared atomic writes crash-durable with truthful failure semantics.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit the write, replace, close, and storage-synchronization sequence.
2. Define success only after file content and the parent directory are synced.
3. Preserve the old destination when content sync or replacement fails.
4. Distinguish post-replace directory-sync uncertainty from pre-replace failure.
5. Preserve primary and cleanup failures, including process interruptions.
6. Verify operation ordering, filesystem outcomes, and exception provenance.
7. Run full quality gates, commit, and push.

## Out Of Scope

- Append-only logs retain their separately documented process-visible,
  non-`fsync` contract in this batch.
- SQLite durability remains governed by SQLite journal and synchronous modes.
- No hidden retries are added to write, sync, replace, or cleanup operations.

## Completion Evidence

- `write_text_atomic(...)` now synchronizes the complete `0600` temporary file
  before replacement and synchronizes its `0700` parent directory afterward.
- File-sync and replace failures leave the previous destination authoritative
  and remove the owned temporary file.
- Cleanup runs for ordinary exceptions and `BaseException` interruptions while
  preserving dual-failure provenance through `AtomicWriteCleanupError`.
- A post-replace directory-sync failure raises
  `AtomicWriteDurabilityError`; the complete new destination remains visible,
  its crash persistence is explicitly uncertain, and the consumed temporary
  pathname is never unlinked.
- Tests verify write/sync/replace/sync ordering, both filesystem outcomes,
  exception causes, interruption cleanup, collision ownership, and existing
  atomic-write behavior.
- Focused storage and atomic-writer consumer suites: `221 passed`.
- Full test suite: `1660 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is ready for publication through `3bda10f`.

## Next Review Batch

Review append-only log durability and batching policy after atomic replacement
has a truthful crash-durable success contract.
