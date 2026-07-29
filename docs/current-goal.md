# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The OpenCode Go protocol matrix and Anthropic configuration publication
are complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Discuss and specify the next objective before implementation.

## Out Of Scope

- No implementation work is active.
- Live provider tests remain outside default pytest and CI and retain explicit
  network/cost opt-in.
- No 0.3.0 release tag until every release-candidate gate is proven.

## Completion Evidence

- The JSON Schema and example configuration now publish the Anthropic API root
  used by the adapter while documenting that one trailing `/v1` is accepted
  and normalized.
- Schema/config/provider focused coverage reported 48 passed. Locked Pyright
  reported 0 errors and 0 warnings; final default pytest reported 2363 passed
  without collecting live-provider tests.
- OpenCode Go live verification now has an explicit five-model, twenty-case
  matrix spanning OpenAI-compatible and Anthropic Messages transports plus
  structured output, NuSelf chat, and tool-plus-final-response behavior.
- The final real OpenCode Go matrix reported 16 passed, 3 strict expected
  failures, and 1 non-strict unstable pass. GLM 5.1, MiniMax M2.7, and Qwen
  3.7 Plus passed every declared layer; DeepSeek V4 Flash's unsupported agent
  capabilities and Kimi K2.6's unstable tool completion are encoded as visible
  capability baselines rather than hidden skips.
- Anthropic SDK URL normalization now converts the public OpenCode Go
  `/zen/go/v1` endpoint to the SDK base without duplicating `/v1/messages`.
  Thinking is explicitly disabled for the tested Anthropic agent path so Qwen
  can use framework-managed tool selection.
- A restarted daemon using the OpenCode Go MiniMax M2.7 Anthropic Messages
  route returned the requested real chat response.
- Locked Pyright reported 0 errors and 0 warnings. Full default pytest reported
  2363 passed, and `uv build` produced both the 0.3.0rc1 sdist and wheel.
- Diagnosis: the OpenCode Go route and OpenAI-compatible provider selection
  are correct. Anthropic Messages semantics return an HTML page on this route.
- Diagnosis: the failed turn reached the provider but returned no LangChain
  `structured_response`; NuSelf exhausted retries, persisted its misleading
  no-API local fallback, and recorded the turn as completed.
- Diagnosis: `nuself dev config` redacted `llm.0.api_key` but also printed the
  raw aggregate `llm.endpoints` value produced by generic flattening.
- The private OpenCode Go endpoint remains `/zen/go/v1` without
  `anthropic: true`; daemon reload and effective-config inspection confirm
  `provider: openai`.
- Effective configuration recursively flattens endpoint sequences to scalar
  leaves and redacts every API key; no aggregate endpoint value is printed.
- Configured endpoint exhaustion now returns visible failure guidance with
  `epistemic_status=unsupported` instead of falsely claiming no API exists.
- Focused config/chat/CLI/LLM coverage: 358 passed.
- `live_tests/` is outside default pytest collection and also requires
  `--run-live-api`; every prompt is fixed synthetic text and no thread, memory,
  persona, source, or runtime prompt is loaded.
- Opt-out verification skips all four live tests without the flag; default
  pytest collects and passes exactly 2346 ordinary tests.
- Real OpenCode Go verification passed all four layers with the
  OpenAI-compatible provider: direct model transport, LangChain typed
  `structured_response`, NuSelf chat response, and tool calling combined with
  a structured final response.
- Locked Pyright reports 0 errors and 0 warnings. The stale hidden daemon was
  terminated; its cleanup removed the active socket, so the active owner was
  cleanly replaced by one ready daemon at PID 31449.
- `nuself dev migrate` now writes a unique sibling database, holds the file
  authority lock while one SQLite transaction copies and read-validates every
  record, then checkpoints, closes, fsyncs, and atomically publishes it.
  Strict migration reads reject corrupt/non-JSON/symlink/nested records and
  missing or filename-mismatched IDs instead of isolating or skipping them.
- Atomic migration, CLI lifecycle, and CLI regression coverage: 333 passed;
  pyright reported 0 errors and 0 warnings.
- Final migration audit now rejects orphan final-name SQLite sidecars and
  proves `auto_backend()` ignores unpublished `.migrating-*` siblings.
  Focused file/SQLite/migration coverage: 136 passed; locked pyright reported
  0 errors and 0 warnings.
- Notification CLI, REPL, evaluator, and daemon delivery now use one frozen
  adapter-plan pipeline. Whole-entry sent/failed mutation APIs are removed,
  dismiss retains the complete plan/history, and recovery skips both sent and
  failed terminal adapter results before finalizing global status.
- Focused notification and CLI coverage: 349 passed; pyright reported 0
  errors and 0 warnings. The source scan finds no remaining `mark_sent` or
  `mark_failed` caller or implementation.
- A durability-uncertain final candidate write now permits compensation only
  after a successful read proves the candidate absent or non-accepted.
  Candidate/target observation failures and accepted candidates with
  unexpected targets remain typed ambiguous commits with secondary errors and
  no destructive rollback.
- Focused candidate, curator, and optimizer coverage: 93 passed; pyright
  reported 0 errors and 0 warnings.
- Project metadata now requires uv `0.11.21` and dev-locks Pyright `1.1.411`.
  CI and release use `--locked` sync/run commands; release has a full-history
  checkout, verifies an annotated tag on main, and reruns locked Pyright plus
  the complete pytest suite before any build or publication effect.
- Release/workflow contract coverage: 12 passed; `uv lock --check`, locked
  pyright, and YAML parsing passed.
- Final locked local gate: Pyright reported 0 errors and 0 warnings; full
  pytest reported 2341 passed.
- Final `uv build` produced the 0.3.0rc1 sdist and wheel. A fresh uv-managed
  Python 3.14 environment installed that wheel and all declared runtime
  dependencies; CLI/runtime/storage/email imports and installed
  `nuself --version` passed.
- The `bd43f1d` external review has been re-audited requirement by requirement:
  all five release blockers have direct implementation, fault-injection or
  contract tests, and full-gate evidence. The two explicitly non-blocking
  ThreadStore follow-ups are recorded in `TODOs.md`.
- Final code CI run `30466563141` passed all six Linux/macOS and Python
  3.12-3.14 jobs, including pinned uv installation, locked Pyright, 2341
  tests, distribution builds, and clean-wheel smoke tests.
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
- Final full pytest release gate after migration/provenance work: 2322 passed.
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
- All executable CI/release actions are pinned to immutable 40-character
  commits with readable release labels. Release now grants explicit content,
  OIDC, and attestation permissions, generates SHA256SUMS, and attests every
  distribution/checksum artifact before one release-upload step.
- Workflow and release-contract coverage: 6 passed; both workflow files parse
  as YAML.
- The final `uv build` rerun produced the 0.3.0rc1 sdist and wheel in an
  isolated temporary output directory.
- Final full pyright after migration/provenance work: 0 errors, 0 warnings.
- Final full pytest rerun after the pyright-driven wire-type narrowing:
  2322 passed.
- The original external review has been re-audited item by item against the
  current tree. All 13 code findings and every RC engineering deliverable have
  implementation plus focused regression evidence.
- Final code CI run `30462105808` passed all six Linux/macOS and Python
  3.12-3.14 jobs, including pyright, 2322 tests, distribution builds, and
  clean-wheel smoke tests.

## Publication

The reviewed implementation is published on `dev/v0.3.x`; the goal-closure
commit is the branch tip.

## Next Review Batch

None selected. Await the next user-directed feature or review objective.
