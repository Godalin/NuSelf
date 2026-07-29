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
8. Gate the file-to-SQLite upgrade with frozen 0.2.5 private data.
9. Run focused fault injection and full quality gates; commit by functional
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
- `delete_file_durable()` now makes file-collection deletion symmetric with
  atomic replacement: a post-unlink directory-sync failure retains the visible
  deletion and raises `AtomicDeleteDurabilityError`.
- Focused storage/candidate/notification deletion tests: 107 passed; pyright
  reported 0 errors and 0 warnings.
- Candidate acceptance now recognizes storage mutations that are already
  visible but not proven crash-durable. Pending candidates compensate target
  create/merge/delete mutations; visibly accepted candidates with matching
  targets raise a typed ambiguous-commit error without destructive rollback.
- Focused candidate, curator, and optimizer tests: 86 passed; pyright reported
  0 errors and 0 warnings.
- File backend transactions now use one stable cross-process advisory lock with
  safe same-thread nesting. Notification outbox idempotency lookup and insert
  run in one backend transaction; a spawned-process contention test proves one
  durable entry wins for one shared idempotency key.
- Focused notification, file-storage, and candidate tests: 94 passed; pyright
  reported 0 errors and 0 warnings.
- Outbox entries now freeze stable required adapter IDs on first delivery and
  persist each adapter result before invoking the next one. Interrupted pending
  delivery resumes without repeating adapters already recorded as sent;
  duplicate adapter IDs fail before external effects.
- Focused outbox, delivery-loop, email, and macOS adapter tests: 60 passed;
  pyright reported 0 errors and 0 warnings.
- Reason export now schedules delayed online reconciliation when composition
  failure state cannot be persisted or retry enqueue callbacks fail. Shared
  delayed scheduling invokes callbacks outside its lifecycle lock and exposes
  callback failures to a domain observer after releasing task ownership.
- Focused scheduling, export recovery, and Reason audit tests: 122 passed;
  pyright reported 0 errors and 0 warnings.
- ThreadState now rejects non-object or non-exact messages, boolean indexes,
  and any explicit next index that differs from start plus retained message
  count. Runtime state updates now produce that invariant directly; only a
  missing legacy next index is derived.
- Thread/chat/curator/CLI/reflection coverage: 500 checks passed across the
  main run and corrected fixture rerun; pyright reported 0 errors and 0
  warnings.
- The curator fast gate now checks a shared union of English,
  Simplified/Traditional Chinese, and Japanese durable markers. Chinese,
  Japanese, and mixed-language short-turn tests prove the model boundary is
  reached and a candidate is staged.
- Focused memory-curator tests: 41 passed; pyright reported 0 errors and 0
  warnings.
- Endpoint availability classification now includes structured 408, 500, 502,
  503, and 504 statuses while retaining endpoint-specific authentication,
  permission, payment, and rate-limit failover. Direct, response, cause,
  context, boolean, client-status, and no-message-parsing cases are covered.
- Focused structured/text/chat endpoint tests: 70 passed. The batch pyright
  rerun remains pending because the tool cache attempted a blocked network
  refresh and the subsequent approval service disconnected.
- Email delivery now builds messages inside its declared failure boundary,
  escapes body and link attributes, canonicalizes only supported `nuself`
  deep links, rejects fragments/external schemes, and rejects configuration
  header control characters.
- Focused email, deep-link, and notification-loop tests: 61 passed.
- Job admission, delayed scheduling, and owned calls now use one shared finite
  non-negative timeout validator; bool, NaN, infinity, and negative cases are
  consistent.
- Focused runtime job/scheduling/execution/export tests: 63 passed.
- Thought-pack export validation now rejects trailing dots and
  case-insensitive Windows device names, including reserved first components
  followed by another extension.
- Focused pack tests: 28 passed.
- Package and runtime fallback metadata now identify `0.3.0rc1`. Versioning
  names `dev/v0.3.x`, explicitly supports Linux/macOS, and documents Windows
  as unsupported while POSIX locks and Unix sockets remain required.
- CI now covers Python 3.12-3.14 on Ubuntu and macOS. Release uses the same
  `uv build`, a clean-wheel CLI smoke, SHA256 checksums, and a tested gate for
  exact tag/project/runtime/changelog agreement.
- Release-gate and CLI-version tests: 5 passed; `nuself --version` printed
  `nuself 0.3.0rc1`.
- Full pytest release gate: 2317 passed.
- `uv build` produced `nuself-0.3.0rc1.tar.gz` and
  `nuself-0.3.0rc1-py3-none-any.whl` in an isolated temporary directory.
- A clean uv-managed Python 3.14 environment installed the wheel and all
  declared runtime dependencies from the package index; import smoke and the
  installed `nuself --version` command passed.
- A frozen 0.2.5 private-data fixture now migrates file-backed memory,
  notification, and reasoning records into SQLite and is read through current
  repositories. The migration explicitly normalizes legacy memory relation
  fields while malformed relation shapes remain fail-closed.
- Focused storage migration and memory repository coverage: 94 passed.
- Full pyright remains the only local gate pending after its cache attempted a
  blocked refresh and the explicit retry approval service disconnected.
- Remaining external findings require fault-injection or contract-level
  verification before implementation.

## Publication

Work begins after the completed infrastructure review at `c0a82e3`.

## Next Review Batch

Pinned release automation, build provenance, and full validation.
