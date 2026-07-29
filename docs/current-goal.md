# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close the confirmed correctness, persistence, and security gaps that block a
trustworthy 0.3.0 release candidate.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Contain every file-backend collection key and reject record/key mismatch.
2. Serialize ThreadStore lifecycle operations with stable cross-process locks.
3. Preserve valid zero-valued memory importance and scan analogous defaults.
4. Define and repair ambiguous file commits plus crash-durable deletion.
5. Persist notification delivery state per adapter and make idempotent add
   atomic.
6. Repair confirmed online recovery, strict decode, failover, multilingual
   curation, email safety, timeout, and portable-name issues.
7. Align version/release/platform contracts and add release-candidate gates.
8. Run focused fault injection and full quality gates; commit by functional
   boundary, push, and confirm final development-branch CI.

## Out Of Scope

- No unrelated user feature or new agent capability.
- No compatibility shim when all in-repository callers can migrate directly.
- No claim that an external review item is fixed before reproducing it against
  the current tree.
- No 0.3.0 release tag until every release-candidate gate is proven.

## Completion Evidence

- Confirmed: `_FileCollection.get/put/delete` directly interpolate untrusted
  keys into paths and `list` recursively follows nested JSON paths.
- Confirmed: ThreadStore rename, branch, archive, unarchive, and delete bypass
  thread locks; rename/archive/delete also remove stable lock files.
- Confirmed: three memory decoders use `optional_float(...) or default`, so
  valid `importance=0.0` changes value during round-trip.
- File collection keys are now centrally validated; direct-child containment,
  record/key identity, and symlink rejection have focused get/put/delete/list
  coverage.
- Focused file-storage, migration, and corrupt-record tests: 61 passed;
  pyright reported 0 errors and 0 warnings.
- Thread lifecycle operations now lock every source/destination identity in
  lexical order and never unlink lock files. Spawned-process tests prove
  source and destination contention plus rename of the latest committed
  snapshot.
- Focused ThreadStore/chat/CLI lifecycle tests: 70 passed; pyright reported 0
  errors and 0 warnings.
- Entry, candidate, generic memory object, profile, and evaluation numeric
  decoders now distinguish missing fields from zero and reject booleans.
  Repository round-trips prove `0.0`, interior values, `1.0`, missing defaults,
  and invalid booleans.
- Focused memory/profile/eval tests: 94 passed; pyright reported 0 errors and 0
  warnings. The source scan finds no remaining optional-number `or default`
  pattern.
- Remaining external findings require fault-injection or contract-level
  verification before implementation.

## Publication

Work begins after the completed infrastructure review at `c0a82e3`.

## Next Review Batch

File mutation commit-state and durable-delete semantics.
