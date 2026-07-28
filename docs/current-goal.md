# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Reconcile duplicate log identities consistently across full, rotated,
incremental, and non-file activity reads.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit full-reader, rotation-overlap, cursor, and `mark_seen()` identity state.
2. Specify exact duplicate versus conflicting duplicate behavior.
3. Add one canonical record fingerprint per seen identity.
4. Share reconciliation across full and incremental readers.
5. Verify exact deduplication and cross-batch conflict diagnostics.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep the chronologically first record as canonical.
- Do not expose event IDs or record payloads in conflict diagnostics.
- Preserve content-derived identity for legacy records without event IDs.

## Completion Evidence

- Full and incremental readers share canonical-record fingerprint
  reconciliation after chronological sorting.
- Exact rotated/active and activity/file overlaps are silently deduplicated;
  the chronologically first record remains canonical.
- Reused event IDs with different content suppress the later record and emit
  one aggregate warning without IDs, payloads, messages, metadata, or paths.
- `InteractiveLogCursor.mark_seen(...)` retains fingerprints across transport
  and file batches instead of recording identity alone.
- Focused log, CLI, and REPL activity tests: `358 passed`.
- `.venv/bin/pytest -q`: `1542 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `a6bebbf`.

## Next Review Batch

Audit log retention and rotation recovery under filesystem failures.
