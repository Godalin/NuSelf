# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

In progress — continuously audit and simplify while preserving composability.

## Current Phase

Remove REPL startup's redundant configuration-error catch.

## Ordered Steps

1. Specify readiness as the owner of expected configuration diagnostics and
   application composition as fail-fast after readiness.
2. Remove the broad REPL notice catch that misclassifies graph/storage errors
   as invalid configuration.
3. Add a propagation regression, run focused/full gates, record evidence, and
   commit without pushing.

## Exclusions

- Preserve readiness actions, missing-model notice, authority mismatch notice,
  recent-failure aggregation, and outer CLI cleanup/error handling.
- Do not duplicate readiness parsing inside REPL or add a generic fallback.

## Constraints

- Preserve domain-owned registries, semantic validators, service APIs, durable
  recovery, and the single-scheduler daemon.
- Add no generic bus, facade hierarchy, compatibility shim, worker, or lock.
- Keep each reduction independently tested and committed; do not return this
  board to Idle while the persistent review goal remains active.

## Phase Evidence

- REPL startup notices now consume the composed graph without catching
  `OSError`/`ValueError` as configuration failures. Expected invalid config is
  already owned by command readiness; storage and composition failures retain
  their real type for the outer lifecycle boundary. A regression proves an
  application `OSError` propagates instead of producing a misleading notice.
  Focused readiness/REPL/CLI tests: 336 passed; full suite: 2445 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Daemon chat now reads `request_timeout_seconds` directly at its
  `client.chat()` call. Removed the single-use timeout getter and three tests of
  that internal getter; one adapter-boundary regression now proves the actual
  workspace request inherits and transmits the user-layer timeout. Focused
  chat/CLI tests: 341 passed; full suite: 2444 passed; Pyright: 0 errors, 0
  warnings; sdist and wheel build succeeded.
- `ApplicationRuntime.application` and `.backend` now share one lock-owned lazy
  backend acquisition primitive, eliminating duplicate resource creation
  branches. Close also releases the graph reference while retaining idempotent
  backend cleanup and diagnostics. A mixed concurrent-access regression proves
  one backend open and one graph composition. Focused runtime/composition tests:
  49 passed; full suite: 2446 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- Daemon chat timeout selection and REPL startup notices now consume the
  already-composed `ApplicationGraph.config`; removed their independent
  path-only `ConfigSystem.load()` calls. Ordinary process surfaces therefore
  share one immutable effective config, while explicit scope inspection remains
  independent. A workspace regression proves user-layer timeout inheritance.
  Focused config/chat/REPL tests: 39 passed; full suite: 2445 passed; Pyright:
  0 errors, 0 warnings; sdist and wheel build succeeded.
- The CLI composition root now binds the reply printer and memory-curator
  callback directly with standard partial application. Removed three private
  single-use forwarding functions plus their type-only imports; entrypoint
  policy and callback protocols remain unchanged. Focused CLI/REPL tests: 340
  passed; full suite: 2444 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- Removed the handwritten `PeriodicTaskKind` subset. The immutable recurring
  registration sequence is now bounded by the sole closed `DaemonTaskKind`, so
  adding or removing periodic membership requires one data edit rather than a
  parallel type-catalog edit. Handler coverage and runtime task validation are
  unchanged. Focused scheduler/state tests: 63 passed; full suite: 2444 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Daemon client requests now call the Unix socket `connect()` operation
  directly instead of first checking path existence. This removes a TOCTOU
  branch and makes missing sockets retain the same connect-phase `OSError`
  cause as stale or otherwise unusable sockets. Focused transport/chat/lifecycle
  tests: 116 passed; full suite: 2444 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `DaemonRestartResult` now contains only its stop and start transitions; final
  status is read from `start.status` instead of a duplicate forwarding
  property. Audit, one-shot CLI, and REPL presentation use that authoritative
  path with unchanged metadata and output. Focused lifecycle/CLI/REPL tests:
  446 passed; full suite: 2444 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- Daemon startup now serializes the resolved user root and optional workspace
  root, and the child reconstructs one `NuSelfScope` through `resolve_scope()`
  before opening its application runtime. CLI lifecycle callers preserve that
  scope while status, stop, audit, and process ownership remain rooted at the
  selected authority. Spawn and entrypoint regressions cover both halves of the
  process boundary. Focused daemon/CLI tests: 428 passed; full suite: 2444
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `open_application_runtime()` now accepts an explicit `NuSelfScope`, and CLI
  main passes the scope it already resolved rather than only `scope.root`.
  Path-based internal/test callers remain supported; a regression proves the
  exact workspace scope reaches `RuntimePaths`. Focused scope/runtime/CLI tests:
  42 passed; full suite: 2442 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- `compose_application()` now loads configuration from `paths.scope` instead of
  reconstructing a path-only authority. A new composition regression proves
  workspace graphs inherit user language defaults and apply workspace context
  overrides. Focused configuration/application tests: 23 passed; full suite:
  2441 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `DaemonState`, structural `DaemonRequestState`, request handlers, and the Unix
  socket adapter now expose the selected `authority_root` explicitly. Removed
  the request-state `project_root` name without adding a compatibility property;
  lower-level diagnostic keyword names remain a separate boundary. Focused
  daemon request/socket/state tests: 111 passed; full suite: 2440 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `RuntimePaths` now exposes `authority_root` as its sole canonical root field.
  Migrated application, daemon, storage, memory, Reason, Reflection,
  Notification, Persona, Trace, CLI, and test consumers, then removed the
  explicitly temporary `project_root` property. Boundary search finds no alias
  reads. Focused scope/application/daemon/storage tests: 191 passed; full suite:
  2440 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- System health now uses the observed daemon status directly instead of
  retaining a second `status_unavailable` boolean. Missing authority issues are
  still aggregated before the unavailable status exit. Focused system/CLI/error
  boundary tests: 327 passed; full suite: 2440 passed; Pyright: 0 errors, 0
  warnings; sdist and wheel build succeeded.
- The daemon-list command now renders its fixed header and row directly.
  Removed the single-use `format_daemon_list()` public function while preserving
  exact output, status observation, and exit behavior. Focused daemon
  CLI/lifecycle tests: 373 passed; full suite: 2440 passed; Pyright: 0 errors, 0
  warnings; sdist and wheel build succeeded.
- CLI daemon lifecycle failures now use the shared safe diagnostic formatter at
  their presentation sites. Removed the lifecycle-specific one-line forwarding
  function and its imports while leaving shared start/stop/restart audit
  orchestration intact. Focused lifecycle/CLI/entrypoint tests: 379 passed; full
  suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- Raw daemon socket request transport is now private to `client.py`; production
  callers use only the seven typed operations. Low-level transport and CLI
  retry/error tests retain direct control of the private seam without adding a
  client class or facade. Focused daemon transport/CLI tests: 362 passed; full
  suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- Generic daemon successful-response decoding is now private to `client.py`;
  the public client surface consists of typed protocol operations. Replaced two
  helper-level tests with `health()` boundary tests that still prove application
  failure and malformed-payload classification. Focused daemon client/transport
  tests: 65 passed; full suite: 2440 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `DaemonStopError` now exposes ownership only through its authoritative
  `status` snapshot. Removed the duplicate `owner_active` forwarding property;
  lifecycle audit reads `error.status.owner_active` directly and preserves the
  same true/false/unknown projection. Focused lifecycle/audit tests: 73 passed;
  full suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- `ChatResponsePayload.from_wire()` now owns confidence presence, numeric type,
  conversion, and range validation in one block. Removed the sole-use generic
  `_optional_number()` helper without weakening null/bool/NaN/infinity rejection.
  Focused daemon payload/handler tests: 28 passed; full suite: 2440 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `ChatRequestPayload.from_wire()` now owns its two optional ID defaults and
  strict decoding directly. Removed a two-call helper, two overload
  declarations, and the `overload` import while preserving message-first
  validation and all wire behavior. Focused daemon payload/handler tests: 28
  passed; full suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and wheel
  build succeeded.
- `LogOnlyNotificationAdapter` now receives the resolved project `Path`, like
  the email and macOS adapters, instead of retaining `RuntimePaths` solely to
  extract one field. No adapter hierarchy or authority wrapper was added.
  Focused Notification tests: 76 passed; full suite: 2440 passed; Pyright: 0
  errors, 0 warnings; sdist and wheel build succeeded.
- Notification adapter composition now receives only `EmailConfig` and
  `MacosNotificationConfig` from application composition instead of the full
  `SystemConfig`. No wrapper type or new layer was added; adapter ordering and
  log-only fallback are unchanged. Focused notification/daemon/CLI tests: 750
  passed; full suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded. One concurrent Memory test timed out only while gates
  ran in parallel, then passed alone and in the serial full-suite rerun.
- macOS AppleScript escaping is now a private module implementation detail
  consumed only by `send()`. Replaced two direct helper tests with one stronger
  assertion over the exact emitted `osascript` command covering quotes and
  backslashes. Focused macOS adapter tests: 8 passed; full suite: 2440 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `MacOSNotificationAdapter` now keeps its construction-time `osascript`
  discovery result private. Tests control `shutil.which()` before construction
  rather than mutating adapter state; no sentinel or alternate constructor was
  added. Focused macOS/delivery tests: 36 passed; full suite: 2441 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `MacOSNotificationAdapter` now requires one composition-resolved project
  `Path`. Removed its optional authority input and internal `runtime_paths()`
  import/call; dry-run, executable discovery, timeout, audit, and delivery
  behavior are unchanged. Focused Notification/composition tests: 79 passed;
  full suite: 2441 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- Transactional notification admission now performs its one idempotency-key
  scan directly in `add()`. Removed `_find_by_idempotency_key()` and moved the
  cross-process test pause to the real `list()` query boundary; first-entry-wins
  admission remains covered. Focused outbox/delivery tests: 37 passed; full
  suite: 2441 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- Notification outbox state transitions now write their validated immutable
  entries directly to the owned collection. Removed `_write_entry()`, which
  added no transaction, locking, validation, or audit policy, while retaining
  every existing transaction boundary. Focused notification/daemon tests: 105
  passed; full suite: 2441 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- `ActivityBroker.close()` now mirrors the daemon protocol as an idempotent
  command with no return value. Removed the production-ignored boolean and its
  test-only semantics; absence is still proved by the existing rejected-read
  assertion. Focused daemon activity/request tests: 36 passed; full suite: 2441
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `ConversationToolRuntime.prompt_sections()` now directly owns rendering of
  its composed tool registry. Removed the sole-use `_tool_prompt_sections()`
  and `Iterable` import while preserving prompt text, tool order, signatures,
  and descriptions. Focused Chat tests: 182 passed; full suite: 2441 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Chat prompt composition now checks `reason_propose` membership in the
  already-public composed tool registry. Removed the sole-use `has_tool()`
  facade without changing conditional Reason guidance. Focused Chat tests: 182
  passed; full suite: 2441 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- Chat skill registration now computes its ordered explicit-tool intersection
  at the sole use site. Removed `_tools_for_skill()` and the resulting unused
  `AgentSkill` import without changing advisory visibility or drift filtering.
  Focused chat/skill tests: 78 passed; full suite: 2441 passed; Pyright: 0
  errors, 0 warnings; sdist and wheel build succeeded.
- Skill availability now distinguishes intentionally tool-free advisory policy
  from a stale non-empty tool declaration. Advisory instructions remain
  loadable without receiving tools; drifted tool-calling skills remain hidden
  even when matching component tools exist. Focused chat/skill tests: 78
  passed; full suite: 2441 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- Skill capability projection now uses only the ordered intersection of each
  file's explicit `allowed-tools` and the runtime registry. Removed the
  component-label fallback that could mask stale names and broaden authority;
  a drift regression proves a memory skill receives no tools even while memory
  component tools exist. Focused agent/chat tests: 80 passed; full suite: 2441
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Chat tool composition now returns the six base Reason tools without a job
  sink and adds `reason_export` only when scheduling is present. The skill
  loader likewise advertises only skills backed by at least one actual runtime
  tool, removing unavailable export/workspace capabilities from direct chat
  instead of retaining error-only branches. Focused agent/chat/export tests:
  88 passed; full suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- Reason export planning now receives a required `JobSink` at the operation
  boundary instead of retaining an optional sink and unused registry override
  in service state. Chat surfaces without daemon scheduling fail before
  artifact creation; configured surfaces submit exactly one typed job, while a
  real enqueue failure still preserves the durable manifest for recovery.
  Focused Reason output/chat/daemon tests: 97 passed; full suite: 2440 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Reason output planning/composition now writes manifest and progress records
  directly in the owning flows, resolves the sole section-plan fallback at its
  use site, and keeps PDF result classification beside PDF generation. Removed
  four policy-free internal helpers while preserving write order and recovery
  artifacts. Focused Reason output/daemon tests: 22 passed; full suite: 2440
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Reason export body composition now has one truthful service path:
  `compose_with_runner()`. Removed production-zero `compose_job()` plus its
  local renderer, which ignored most runner inputs and could bypass the
  daemon-owned model composition policy; the persistence test now exercises
  the real injected-runner boundary. Focused Reason output/daemon tests: 22
  passed; full suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- `LLMRelevanceGate` now exposes only `score()`, the complete operation used by
  the scheduler. Removed the zero-consumer `passes()` facade that would invoke
  the same model-backed decision and discard cooldown, component scores, and
  reasons. Focused Reflection/daemon tests: 275 passed; full suite: 2440
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `IdeaCandidateGenerator` now accepts only the context, language, authority,
  and typed-agent inputs it consumes. Removed its unused full
  `ReflectionSettings` dependency and composition/test plumbing; scheduling and
  relevance policy remain with their existing owners. Focused
  Reflection/daemon/composition tests: 277 passed; full suite: 2440 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Reason prompt generation is now a required service capability composed by
  `application.reason` from the application-owned paths and immutable config.
  The domain service no longer imports the prompt factory or passes authority
  paths into it; provider endpoints remain lazy until `start_thread`, and
  explicit empty endpoints retain no-model semantics. Focused
  Reason/CLI/Chat/composition tests: 863 passed; full suite: 2440 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Reason endpoint resolution now belongs to `application.reason`, which uses
  the existing graph config when callers omit an explicit tuple. The domain
  `default_reason_advancer()` requires concrete endpoints and no longer imports
  or invokes the configuration/model factory; explicit empty tuples remain
  authoritative. Focused Reason/CLI/REPL tests: 639 passed; full suite: 2439
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `SharedPersonaDiscussionService` now has one construction path requiring a
  resolved project `Path`, `ReflectionSettings`, and language preference.
  Removed full-engine injection and internal `ConfigSystem.load()`; Chat carries
  Reflection settings in its immutable resource snapshot, while narrow agent
  injection remains. Consolidated two construction/delegation tests into one.
  Focused Persona/Chat/Reflection tests: 479 passed; full suite: 2438 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `EmailNotificationAdapter` now requires a resolved `Path` and `EmailConfig`.
  Removed its optional inputs, internal `ConfigSystem.load()`, and
  `runtime_paths()` authority resolution; notification composition remains the
  sole owner of adapter construction. Focused Notification/boundary tests: 133
  passed; full suite: 2439 passed; Pyright: 0 errors, 0 warnings; sdist and wheel
  build succeeded.
- Notification adapter composition now requires the application-owned
  `SystemConfig`. Removed its optional config type, hidden
  `ConfigSystem.load()`, and fallback branch; CLI and REPL pass the same graph
  configuration already used by daemon composition. Focused
  Notification/CLI/REPL tests: 456 passed; full suite: 2439 passed; Pyright: 0
  errors, 0 warnings; sdist and wheel build succeeded.
- Conversation `load()` now directly owns collection lookup and strict decode;
  archive/unarchive directly use immutable dataclass replacement. Removed the
  single-call `_load_unlocked()` and two-call `_with_archived()` forwarding
  helpers without changing public Conversation/history APIs, locks,
  transactions, or stored-record handling. Focused Conversation/CLI/Reflection
  tests: 460 passed; full suite: 2439 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Legacy authority-layout publication now lives only in
  `scripts/migrate_legacy_layout.py`; removed the installed module, top-level
  CLI command/handler/parser, and runtime test location. The moved eight-test
  suite still covers atomic publication, concurrent exclusion, WAL backup,
  transient-file filtering, symlink rejection, and source preservation; CLI
  help explicitly excludes the command. Focused script/CLI/release tests: 342
  passed plus 9 final regressions; full suite: 2439 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded, and all 244 wheel entries exclude
  layout migration code.
- Configuration loading now validates only the current schema. Removed the
  v0.2.5 mutation function, one-time warning cache, legacy-email exception,
  obsolete fixture, and the normalization path parameter used only by that
  shim. Retired `langmem_adapter` input now fails strict validation and an old
  `email.toml` cannot affect or leak into current email validation. Focused
  Config/documentation/boundary tests: 125 passed; full suite: 2439 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Reflection scheduler no longer imports and implicitly re-exports the
  candidate-list and relevance-score Pydantic models it does not consume. Each
  structured output now has one truthful owner/import path while scheduler,
  candidate, and gate behavior remain unchanged. Focused Reflection/boundary
  tests: 160 passed; full suite: 2439 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Chat work admission now checks the scheduler's authoritative `running`
  projection once; that phase already implies `accepting`, which remains in the
  health snapshot for lifecycle visibility. Five periodic handlers retain the
  uniform `DaemonTask` signature through an ignored parameter name instead of
  statement-level deletion. Focused daemon tests: 47 passed; full suite: 2439
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Removed the chat supervisor's unused generic `has_tool_outcomes` property;
  retry safety continues to use the narrower mutating-outcome predicate. Removed
  `SqliteStore.for_project()` and its config dependency so the low-level
  LangGraph store accepts only a composition-resolved database path. Focused
  Chat/workspace tests: 55 passed; full suite: 2439 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- Reason partitioning now uses `list[ReasoningStep]` directly instead of the
  one-helper `ReasonStepList` alias, and Persona discussion imports the exact
  `NonBlankText` constraint already owned by Persona definition rather than
  redeclaring it. Focused Reason/Persona tests: 205 passed; full suite: 2439
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `RuntimeContext.from_record()` now accepts only canonical correlation field
  names. Removed the pre-v0.3.1 chat `thread_id` → `conversation_id` alias and
  its ambiguity branch; strict tests now reject the old spelling while Reason's
  distinct domain `thread_id` remains unchanged. Focused Runtime tests: 110
  passed; full suite: 2439 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- `ConfigSystem` no longer exposes `clear_cache()`, whose only caller was an
  unnecessary test step after creating a previously missing file. Config loads
  still memoize immutable values by path/mtime/size, replace stale entries, and
  never cache missing files; the daemon still adopts changes on restart.
  Focused Config/CLI tests: 79 passed; full suite: 2440 passed; Pyright: 0
  errors, 0 warnings; sdist and wheel build succeeded.
- Removed `ProfileStats` and `profile_stats()`, which had no production, CLI,
  or application-service consumer and were exercised only by their own test.
  Profile CRUD/search/merge/accept remain unchanged; the specification now
  limits immutable statistics snapshots to the real Memory API. Focused
  Profile/Memory/CLI tests: 367 passed; full suite: 2440 passed; Pyright: 0
  errors, 0 warnings; sdist and wheel build succeeded.
- `ToolOutcome` now has one validated construction path. Removed test-only
  `succeeded()`/`failed()` factories and migrated audit/advancer fixtures to
  explicit result/error construction; the LangChain `wrap_tool_call()` hook
  remains unchanged. Focused middleware/audit/advancer tests: 44 passed; full
  suite: 2441 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- `ReasonOutputService` now exposes only the active plan/get/compose/path flow.
  Removed production-zero `start_job()`, `resume_job()`, and `list_jobs()`, their
  private corruption-list helper, and daemon cleanup for an export `.lock` no
  current path creates. Updated the governing specification from synchronous
  locking to scheduler resource-lane serialization; the compose test now uses
  the real plan + compose operations. Focused Reason output/daemon tests: 22
  passed; full suite: 2441 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- Removed the chat runtime's unused `logging` import/module logger and the
  Reason repository's unreferenced storage-version constant. Neither was part
  of observed logging, audit, decoding, or schema validation. Focused
  Chat/Reason tests: 441 passed; full suite: 2443 passed; Pyright: 0 errors, 0
  warnings; sdist and wheel build succeeded.
- `ReasonRepository` no longer contains the zero-caller no-op `ensure()` or
  the raw `get_step()` operation used only by its own test. The application
  continues to expose ordered thread-scoped steps through `ReasonService`, and
  transactional step/thread writes are unchanged. Focused Reason tests: 261
  passed; full suite: 2443 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- `compose_memory_repositories()` now exposes only its two required authority
  inputs. Removed unused memory type and relation registry override parameters
  and imports; direct `MemoryEntryRepository` construction still supports
  focused registry injection. Focused composition/boundary/memory tests: 94
  passed; full suite: 2444 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- Source ingestion now writes its document record directly and retains only
  the non-trivial chunk replacement operation as a private method. Removed the
  one-line, single-caller `_save_document()` forwarding method without changing
  the public API. Focused Source/CLI tests: 322 passed; full suite: 2444 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Source document persistence is now private to `ingest_path()`, matching the
  already-private chunk replacement operation. Four CLI fixtures now ingest
  real temporary files instead of constructing partial stored documents; no
  raw-write alias remains. Focused Source/CLI tests: 322 passed; full suite:
  2444 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Source chunk replacement is now private to `ingest_path()`, its sole
  consumer. Removed an independently exposed partial-write API while preserving
  complete document/chunk ingestion, re-ingestion replacement, queries,
  deletion, and candidate extraction. Focused Source/CLI/Memory/Reflection
  tests: 385 passed; full suite: 2444 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `MemoryEntryRepository.list_relations()` now directly owns its one-shot
  relation projection and filter. Removed the sole-use `_compute_relations()`
  method; descriptors, record order, endpoint handling, and CLI output remain
  unchanged. Focused Memory/CLI/REPL tests: 357 passed; full suite: 2444
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Removed the zero-consumer `MemoryEntryRepository.save_object()` adapter,
  which redundantly validated a `MemoryObject`, converted it, and forwarded to
  `save()`. Canonical writes remain `save(MemoryEntry)` while legacy
  object-shaped record decoding remains intact. Focused Memory/storage/data
  tests: 211 passed; full suite: 2444 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `MemoryEntryRepository.compute_graph()` now directly owns symbolic graph
  construction, and node/edge search, path finding, closure, and external
  retrieval expansion all reuse it. Removed the private implementation mirror
  and public pass-through without adding cache or state. Focused Memory/chat
  tests: 128 passed; full suite: 2444 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Reflection dismiss/archive status decisions now live in `ReflectionService`,
  and duplicate archival remains in `ReflectionOrganizer`; each saves the
  already-resolved entry directly. Removed both repository use-case methods and
  their duplicate reads, replacing repository tests with direct service
  coverage of status, reviewed timestamp, and persistence. Focused
  Reflection/CLI/REPL tests: 428 passed; full suite: 2444 passed; Pyright: 0
  errors, 0 warnings; sdist and wheel build succeeded.
- `ReflectionRepository` now exposes one truthful stable-ID `save()` operation
  for both creation and replacement. Removed identical `add()`/`update()` APIs
  and migrated scheduler, organizer, tests, and adapters without compatibility
  aliases; dismiss/archive retain their status-transition semantics. Focused
  Reflection/chat/CLI tests: 496 passed; full suite: 2444 passed; Pyright: 0
  errors, 0 warnings; sdist and wheel build succeeded.
- Reason pause, resume, resolve, and archive remain distinct public use cases,
  while `_transition()` now owns their common ID-or-index resolution alongside
  validation, persistence, and audit. Removed four repeated resolution steps
  without exposing a generic status setter. Focused Reason/CLI/REPL tests: 360
  passed; full suite: 2444 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- `ReasonService.advance_thread()` now resolves its optional operation inputs
  into one concrete `ReasoningStep` before any mutation. Removed the empty
  success branch, nine impossible downstream null fallbacks, and the one-use
  optional-summary helper; state, persistence, trace, and audit paths now share
  the same non-null domain invariant. Focused Reason tests: 61 passed; full
  suite: 2444 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- `ReasonService` no longer accepts or stores a constructor-time advancer,
  which production composition never supplied. `advance_thread()` now has one
  explicit operation boundary: receive either that call's narrow advancer or
  an already-generated structured step. Updated the sole test that relied on
  the hidden fallback. Focused Reason/CLI/REPL tests: 585 passed; full suite:
  2444 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `ReasonScheduler` now requires its `ReasonAdvancerProtocol` capability at
  construction. Every production and test composition already supplied it;
  removed the unused optional type/default and the runtime branch that could
  silently disable background advancement. The scheduler remains decoupled
  from the concrete model-backed advancer. Focused Reason scheduler/daemon
  tests: 177 passed; full suite: 2444 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `ReasonOutputService.job_paths()` now directly owns validation and path
  construction, and all service methods plus daemon processing reuse it.
  Removed its private pass-through, a one-use export-root helper, duplicate
  daemon manifest assembly, and the one-call enqueue closure/boolean while
  preserving sink failure isolation and audit ordering. Focused Reason
  output/daemon tests: 24 passed; full suite: 2444 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- `PrivateWorkspacePaths` now contains only its distinct owner export root and
  shared authority database. Removed the unused `notes` path and the
  `artifacts` alias that was always identical to `root`; Reason output and
  daemon recovery derive their writer-owned `jobs/` paths from `root`.
  Focused workspace/reason/daemon tests: 269 passed; full suite: 2444 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Reason service, advancer, and output composition now call
  `PrivateWorkspaceStore.paths()` directly. Removed `ensure()`, a no-op alias
  that created no directory or resource, and aligned workspace validation
  tests with the truthful resolver API. Focused workspace/reason tests: 74
  passed; full suite: 2444 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- Memory and profile stats now convert standard-library `Counter` results to
  ordinary dicts at their domain-owned call sites. Removed both identical
  private counting loops without adding shared infrastructure; implementation
  removes 19 lines and adds 11. Focused memory/profile tests: 58 passed; full
  suite: 2444 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- `build_notification_adapters()` now returns its canonical ordered plan as an
  immutable tuple. All consumers already only iterate or pass it to delivery;
  no collection wrapper or compatibility path was added. Added a direct tuple
  contract assertion. Focused notification/CLI tests: 348 passed; full suite:
  2444 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `NotificationDeliveryLoop` now validates and indexes its adapter sequence at
  composition, then reuses that private ordered plan for every poll and entry.
  Standalone single-entry delivery still validates at its own boundary. Added
  a regression proving later mutation of the caller's list cannot change the
  live worker. Focused notification/daemon tests: 52 passed; full suite: 2444
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `ReflectionOrganizer` now requires an explicit `Path` project root. Removed
  its unused `None` default so successful merge observations remain scoped to
  the application graph's selected authority; all existing callers already
  supplied that path. Focused reflection tests: 53 passed; full suite: 2443
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `ReasonScheduler` and its test composition now require an explicit `Path`
  project root. Removed the unused `None` default that could send background
  failure observations outside the selected authority; every existing caller
  already supplied the resolved path. Focused reason/daemon tests: 30 passed;
  full suite: 2443 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- Reason scheduler test composition now accepts `ReasonAdvancerProtocol`, and
  six structural test doubles satisfy its named `thread` parameter directly.
  Removed the concrete advancer import and all forced casts that previously hid
  the fixture's stale coupling. Focused scheduler tests: 7 passed; full suite:
  2443 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `ReasonScheduler` now types its injected advancer as the existing
  `ReasonAdvancerProtocol` rather than the concrete model-backed class. It still
  receives the same production object, but its declared dependency now matches
  the sole `advance(thread)` capability it uses and existing test doubles.
  Focused reason/daemon tests: 53 passed; full suite: 2443 passed; Pyright: 0
  errors, 0 warnings; sdist and wheel build succeeded.
- Daemon memory-curation, conversation-compression, and shared durable
  follow-up admission now return `None`. Removed an unconsumed success/deferred
  boolean while retaining typed capacity/stopped handling, `task.deferred`
  observation, and periodic durable rediscovery. Focused daemon tests: 33
  passed; full suite: 2443 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- The daemon reflection task now calls `ReflectionScheduler.reflect()` once;
  removed its redundant `should_reflect()` preflight. Reflection retains sole
  ownership of schedule gates and blocked-cycle audit, and one periodic wake-up
  can no longer sample interval jitter twice. The daemon regression mock now
  exposes only the operation the handler needs. Focused daemon/reflection tests:
  71 passed; full suite: 2443 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- Conversation and notification lock call sites now rely on the shared lock
  primitive's existing parent-path preparation. Removed both redundant
  `ensure_private_directory()` calls and imports while retaining identical
  managed permissions, symlink checks, lock paths, and blocking behavior.
  Implementation removes 10 lines and adds 2. Focused tests: 50 passed; full
  suite: 2443 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- Conversation and notification resource locks now reuse
  `blocking_private_file_lock()` for owner-only file preparation and blocking
  `flock` lifecycle. Removed both duplicate stateful lock classes while each
  domain retains its own resource identity and mutation scope; specialized
  lock contracts remain separate. Implementation removes 65 lines and adds
  30. Focused private-filesystem/conversation/notification tests: 50 passed;
  full suite: 2443 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- `_reject_visible_tool_call()` now checks its single protocol-leak marker
  directly. Removed the one-use `_looks_like_tool_call()` classifier while
  preserving both structured and compatible-message rejection paths and the
  typed invalid-output error. Focused chat response/agent tests: 95 passed;
  full suite: 2443 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- Unconfigured-model and exhausted-configured-endpoint fallback builders now
  share `_last_user_text()`. Removed duplicate reverse prompt scans while
  retaining distinct cause guidance and the configured-failure `unsupported`
  epistemic status. Focused chat response/agent tests: 95 passed; full suite:
  2443 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Memory search now queries/renders at its sole REPL branch and reflection
  indentation stays at its sole list loop. Removed the public one-use
  `handle_interactive_memory_search()` and `indent_lines()` helpers without
  changing output. Focused REPL/CLI tests: 570 passed; full suite: 2443 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Interactive reflection pending/all views now share one reflection handler,
  and notification pending/all views share one notification handler. Dispatcher
  selects `include_all`; removed two public list functions and duplicate
  repository/render loops without a cross-domain renderer. Focused REPL/CLI
  tests: 570 passed; full suite: 2443 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Interactive Reason show/advance/pause/resume/resolve/archive/delete now name
  their ID-or-index input `thread_ref`; removed seven misleading
  `conversation_id` locals while leaving actual chat-history conversation IDs
  untouched. Focused REPL/Reason tests: 328 passed; full suite: 2443 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Interactive memory entry show, candidate review, and source show now call
  `resolve_visible_handle()` instead of maintaining three local
  digit/int/range branches. Stable IDs and list ordering remain domain-owned;
  numeric bounds now use the shared CLI error contract. Added three focused
  regressions. REPL tests: 66 passed; full suite: 2443 passed; Pyright: 0
  errors, 0 warnings; sdist and wheel build succeeded.
- Trace CLI composition now returns the graph-owned `TraceQueryService`
  directly. Removed the recorder-bearing `TraceServices` import and repeated
  `.query` forwarding while keeping the single authority composition entry;
  list/show/search/related behavior is unchanged. Focused trace/CLI tests: 512
  passed; full suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- REPL exit curation now accepts only the selected authority root and scans its
  pending memory observations. Removed the unused session conversation-ID tuple
  from `ReplCallbacks`, cleanup composition, production callback, and tests;
  transcript-before-curation ordering and aggregate cleanup failures remain
  unchanged. Focused REPL tests: 63 passed; full suite: 2440 passed; Pyright: 0
  errors, 0 warnings; sdist and wheel build succeeded.
- Authority ID generation now accepts only the canonical root that actually
  enters the versioned digest. Removed the immediately discarded `ScopeKind`
  argument from the helper and all user/workspace/internal-root call sites;
  same-root selection equivalence and v1 hash bytes are unchanged. Focused
  scope/config tests: 31 passed; full suite: 2440 passed; Pyright: 0 errors, 0
  warnings; sdist and wheel build succeeded.
- Chat persona consultation now writes summary, host-decision, and discussion-
  step audits at their owning lifecycle points. Removed three one-use methods,
  two immediately discarded parameters, and an escalation-reason value that
  never entered behavior or the privacy-safe audit schema. Event ordering and
  metadata remain unchanged. Focused chat/persona tests: 320 passed; full
  suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- Reason workspace tools and thread-local persona tools now receive the same
  `_thread_workspace()` resolver. Removed duplicate closures, imports, authority
  lookup, and namespace construction while retaining per-call runtime-context
  selection and the LangGraph store adapter. Focused Reason/persona tool tests:
  50 passed; full suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- `TraceRecorder.record_reflection_promoted()` now constructs and saves the
  promotion link it owns. Removed the one-use `_link()` repository
  pass-through and the otherwise-unused `TraceRelation` service import;
  identity, relation, summary, and trace-before-link ordering are unchanged.
  Focused trace/reflection tests: 113 passed; full suite: 2440 passed; Pyright:
  0 errors, 0 warnings; sdist and wheel build succeeded.
- Trace, reflection, and Reason command adapters now call one
  `print_json_lines()` terminal-output primitive. Removed three identical local
  printers and their JSON imports while preserving record-owned wire
  conversion, one object per line, sorted keys, and ASCII-safe encoding. The
  source diff removes 28 lines and adds 20. Focused CLI tests: 518 passed; full
  suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- `DaemonState` now borrows `ApplicationGraph` only during construction and
  retains the observation repository as its sole task-time domain repository;
  already-composed chat, curator, reflection, notification, Reason, export,
  and trace capabilities remain independently owned. Daemon tests no longer
  reach through state into the complete graph. Focused daemon/application
  boundary tests: 226 passed; full suite: 2440 passed; Pyright: 0 errors, 0
  warnings; sdist and wheel build succeeded.
- Memory record and payload decoding now share `_expect_str()` and
  `_optional_str()` over `Mapping[str, object]`. Removed three behavior-identical
  dict/mapping validators while retaining accepted values and exact errors;
  list, object, and numeric codecs remain separate. Source removes 37 lines and
  adds 15. Focused memory domain/repository/persona tests: 89 passed; full
  suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- Atomic text and binary writers now use one `_sync_path()` descriptor
  open/fsync/close primitive for temporary files and parent directories.
  Removed duplicate file/directory implementations while retaining call-site
  interpretation of pre-replace cleanup versus post-replace durability errors.
  Focused atomic-write consumer tests: 75 passed; full suite: 2440 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `respond_node()` now invokes its injected response service's `complete()` and
  `finalize()` operations directly. Removed `_complete_response()` and
  `_finalize_draft_response()`, which had one caller each and added no node,
  hook, observation, or policy. Focused chat runtime/response tests: 95 passed;
  full suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- Skipped, started, failed, and completed Reason output chunk definitions now
  share `_chunk_identity()`. Removed the byte-for-byte duplicate completed
  validator while retaining each event's level, status, error policy, duration
  policy, and identity. Focused Reason audit/output tests: 93 passed; full
  suite: 2440 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- Curator and optimizer now call one public `write_memory_audit()` operation.
  Removed two byte-for-byte identical writer façades while preserving the
  optional metadata signature, sealed event registry, exact schemas,
  unknown-event failure, and best-effort sink. Source removes 34 lines and adds
  3. Focused memory audit/curator/optimizer tests: 81 passed; full suite: 2440
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Inlined observation-fragment joining into the sole curator prompt and
  backend-ID filtering into the sole strict plan codec call. Removed
  `_render_observation()` and `_without_storage_id()` while retaining named
  signal, context, corruption, lock, and trace policy boundaries. Focused
  curator tests: 40 passed; full suite: 2440 passed; Pyright: 0 errors, 0
  warnings; sdist and wheel build succeeded.
- Curator plan loading now calls the typed store directly. Removed `_load_plan`,
  which caught a `ValueError` subtype only to emit a generic `ValueError` with
  the same safe message, plus its two sole imports. Corrupt plans still report
  `record_decode_failed`, do not expose record content, and now preserve
  `MemoryCuratorPlanCorruptError`. Focused curator tests: 40 passed; full suite:
  2440 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Curator recovery now uses the same typed `MemoryCuratorPlanStore.get()` as
  operator inspection; removed the identical `resumable()` implementation.
  Observation-ID validation now stays in `exclusive()`, the sole lock-path
  owner, instead of a zero-consumer public helper. Source removes 26 lines and
  adds 3; focused curator-plan/memory/CLI tests: 355 passed; full suite: 2439
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Collapsed the zero-external-consumer visible selection and range classifiers
  into one private `_uses_visible_selection_syntax()` detail. Public shared
  parse/resolve operations remain unchanged, as do numeric indexes, compact
  ranges, deduplication, and hyphenated stable IDs. Focused handle/CLI/REPL
  tests: 327 passed; full suite: 2437 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Removed the zero-consumer `SqliteTransactionError` family root. Rollback-only
  and rollback-cleanup errors remain independently typed direct runtime errors;
  primary/rollback causes and transaction behavior are unchanged. The consumed
  storage-lifecycle error family remains intact. Focused SQLite tests: 111
  passed; full suite: 2437 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- Removed the zero-consumer `HandlerRegistryError` family root. Duplicate,
  sealed, unsealed, coverage, and unknown-key errors remain independently typed
  direct runtime errors; all callers and tests already consume those concrete
  policies. Focused handler/daemon/REPL/CLI tests: 36 passed; full suite: 2437
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `DaemonRequest.request_id` now generates its fresh UUID-hex value directly
  through the dataclass field factory. Removed the zero-consumer
  `new_request_id()` API; explicit IDs supplied by callers or wire decoding are
  unchanged. Focused protocol/client/server tests: 82 passed; full suite: 2437
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Removed the zero-consumer `DaemonSchedulerError` family root. Capacity and
  stopped-admission errors remain independently typed and the daemon still
  handles both as durable follow-up deferral without inspecting error text.
  Focused daemon tests: 169 passed; full suite: 2436 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- Daemon server cleanup, test ownership, and lifecycle failure injection now
  call the sole scheduler's `shutdown()` capability directly. Removed the
  state-level `stop_background_tasks()` pass-through while retaining startup's
  export recovery and periodic admission orchestration. Cleanup ordering,
  aggregated failures, readiness, and scheduler behavior are unchanged.
  Focused daemon tests: 169 passed; full suite: 2436 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- `ChatResult.require_completed_turn()` now owns the single successful-result
  invariant used before post-response projection. Direct CLI and daemon
  adapters call it instead of maintaining duplicate validation; the
  daemon-only helper and unused `CompletedTurn` import are gone. Projection,
  curation, compression, and degraded-result representation remain separate.
  Focused chat/CLI/daemon tests: 119 passed; full suite: 2436 passed; Pyright:
  0 errors, 0 warnings; sdist and wheel build succeeded.
- Removed `AgentCapabilitySnapshot` and its dedicated source module. Daemon
  Reason composition now reuses the endpoint tuple it already owns and asks
  conversation runtime only for copied immutable readonly-tool membership;
  readonly tag filtering and the mutable registry remain encapsulated by the
  tool runtime. Source/tests remove 23 net lines. Focused chat/daemon/reason
  tests: 609 passed; full suite: 2434 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Removed the one-use `SessionHeaderPresenter`, its provider alias, and the
  dedicated `cli/repl/presentation.py` module. Session-header output now lives
  with existing CLI presentation functions; REPL composition binds current
  daemon-status lookup directly into the existing typed callback, so the loop
  remains independently composable. Source/tests remove 20 net lines. Focused
  REPL/CLI tests: 379 passed; full suite: 2434 passed; Pyright: 0 errors, 0
  warnings; sdist and wheel build succeeded.
- Memory optimization and endpoint failover now call their shared classifiers
  directly; the exact pass-through aliases are gone. The sole legacy-email
  migration error now inherits `ValueError` directly because no caller catches
  a migration-error family. The supported v0.2.5 email upgrade remained
  intentionally intact; the then-preserved RuntimeContext alias was removed in
  a later phase recorded above. Focused
  memory/agent/config tests: 188 passed; full suite: 2434 passed; Pyright: 0
  errors, 0 warnings; sdist and wheel build succeeded.
- Removed seven zero-consumer public helpers spanning the obsolete reasoning
  prompt tool factory, old system config handler, memory parsing, tool-result
  conversion, relation rendering, and File-era durable deletion, plus the
  latter's unused dedicated error. Live prompt/config/relation paths remain;
  candidate compensation still covers an authoritative delete failure. The
  implementation/test diff removes 132 net lines, and no public top-level
  definition now has a repository-wide reference count of one. Focused
  reason/memory/CLI/agent/storage tests: 1198 passed; full suite: 2434 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `OwnedCall` now captures one complete copied Python context at construction
  and runs its target inside that context, carrying application authority,
  RuntimeContext, and orthogonal future ContextVars through the owned thread.
  Removed `bind_application_runtime`, `bind_runtime_context`, the nested REPL
  wrappers, and two binder-specific tests; one direct OwnedCall test covers
  complete capture and caller isolation. Focused runtime/REPL/application tests:
  122 passed; full suite: 2434 passed; Pyright: 0 errors, 0 warnings; sdist and
  wheel build succeeded.
- Reflection schedule-state persistence now belongs to the existing
  `ReflectionRepository` through typed read/save operations. Removed the raw
  `ApplicationGraph.reflection_schedule` field, scheduler/gate collection
  constructor parameters, and their direct collection ownership; scheduling
  policy and fail-closed corruption reporting remain in their original owners.
  The schedule-state module now decodes records only and no longer imports the
  storage adapter. Focused reflection/daemon/boundary tests: 183 passed; final
  reflection/boundary rerun: 160 passed; full suite: 2435 passed; Pyright: 0
  errors, 0 warnings; sdist and wheel build succeeded.
- Removed `compose_cli_conversation_store`; conversation commands, REPL
  completion/session/transcript/dispatch, and chat entrypoints now select the
  graph-owned store through the one authority-validating
  `compose_cli_application()` entry. The separate mock surface is gone, while
  `compose_cli_backend()` remains limited to explicit infrastructure commands.
  Focused CLI/REPL/runtime/boundary tests: 629 passed; full suite: 2435 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Reason and memory curation now store their required trace recorder as a
  non-null capability and always enter the existing best-effort trace boundary;
  two unreachable no-recorder branches are gone. Production daemon tasks still
  pass through the closed typed factory, but default context capture and
  explicit durable-context selection now feed one constructor path. Focused
  service/daemon tests: 108 passed; full suite: 2435 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- Removed the production `_default_backends` registry, global backend lock,
  `get/set/reset_default_backend`, and `DefaultBackendResetError`. The manual
  migration script now owns `auto_backend()` with `finally` close; no source,
  script, specification, or boundary rule references the deleted API.
- Direct repository tests use one pytest-scoped backend owner that closes after
  each test. Scheduler threads receive parent-composed resources; spawned
  processes explicitly open and close their own backend instead of inheriting
  hidden state. Focused storage/script/CLI/boundary tests: 204 passed; full
  suite: 2435 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- `ApplicationRuntime` now lazily stores and closes its one
  `ClosableStorageBackend`; graph composition, CLI init/dev/pack operations,
  evaluation, and daemon cleanup all use that same owner. `ApplicationGraph`
  still exposes no raw backend, and legacy layout migration no longer resets a
  process-global cache it never populated.
- Runtime construction remains storage-lazy, first backend/graph access remains
  serialized by the existing lifecycle lock, close remains idempotent, and a
  composition failure inside the runtime context closes the selected backend.
  Focused runtime/CLI/eval tests: 360 passed; full suite: 2438 passed; Pyright:
  0 errors, 0 warnings; sdist and wheel build succeeded.
- Daemon lifecycle audits now compose the same sealed
  `AuditDefinitionRegistry`/`AuditEventDefinition` contract as daemon request
  and transport audits. The lifecycle-only definition class, registry adapter,
  schema error, exact-field validator, and compatibility aliases were removed;
  domain messages and transition/failure validators remain local.
- This audit-infrastructure unification removes 200 lines while adding 154
  across code, tests, and governing specifications. Focused audit/lifecycle/
  infrastructure tests: 111 passed; full suite: 2437 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- Lifecycle/result and Reason-export call-graph audit found both typed boundaries
  semantically active: lifecycle transitions feed CLI audit/rendering, while the
  export service owns durable recovery/retry policy and delegates execution to
  the single daemon scheduler. Neither was replaced by a generic facade.
- Daemon start and stop now each have one timeout construction/raise exit rather
  than duplicated pre-probe and pre-sleep branches. Focused lifecycle/export/
  boundary tests: 129 passed; full suite: 2437 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- Reason-output and hardcoded-constant specifications now describe scheduler
  task identity, resource-lane serialization, startup recovery, and the actual
  30-second shutdown ownership timeout; stale private queue/worker constants
  and contracts are gone.
- Removed the shared derived-file writer, five repository/service reindex APIs,
  automatic post-mutation rewrites, and the memory/profile/trace reindex CLI
  surface. Direct memory graph/relation/search and trace queries remain backed
  by the injected SQLite repositories; explicit exports are unchanged.
- The change deletes 319 lines while adding 77 lines, mostly specification and
  goal evidence. Focused memory/profile/source/reason/CLI tests: 383 passed;
  full suite: 2437 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build
  succeeded.
- The remaining large REPL command and dispatcher modules have no dead public
  handlers or duplicated parser boundary: the sealed handler table exactly
  covers registry command identities, while metadata and execution remain
  separate. A mechanical domain split would add files without reducing the
  call graph, so they remain intact.
- Runtime-event persistence and daemon live activity cannot be registered as
  parallel projections without adding a second envelope-to-log conversion:
  the publisher carries `RuntimeEnvelope`, while the unified activity stream
  intentionally carries persisted-form `LogEvent`. The existing bounded log
  sink observer remains the one conversion point.
- CLI parsing, daemon audit definitions, storage backends, and shared
  observability now import `LOG_COMPONENTS`, `LogComponent`, and `LogLevel`
  directly from neutral `runtime.audit_types`; they no longer load the log
  persistence module merely to describe contracts.
- Logging/runtime/daemon focused suite: 216 passed. Post-boundary
  `uv run --locked pytest -q`: 2452 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Audit-envelope construction/persistence and runtime-event projection remain
  explicit public contracts with distinct validation and failure semantics.
  Removed the undocumented `log_event_key` pseudo-API; stable/legacy identity
  selection now stays inside the sole reconciliation algorithm that uses it.
- Log read/cursor focused suite: 104 passed. Post-identity cleanup
  `uv run --locked pytest -q`: 2452 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `LogEvent` and its record codec now live in neutral `runtime.log_event`.
  Twenty production consumers use that model without importing filesystem
  paths, private-file hardening, `flock`, rotation, or append recovery.
- `logs.py` consumes the model through a private alias and no longer re-exports
  `LogEvent`; executable boundary tests enforce both dependency directions.
- Log-model/runtime/daemon/UI focused suite: 270 passed. Post-model split
  `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Shared observability helpers with domain callers or distinct contract tests
  remain public. The internal event-delivery failure interpreter is now private
  to `publish_observed_event`; no standalone production caller existed.
- Observability/chat focused suite: 112 passed. Post-helper cleanup
  `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `ConversationGraphRuntime` now requires a complete `EventPublisher` and no
  longer imports log persistence or constructs standalone observability.
  Application composition owns the standalone publisher/log projection;
  daemon composition continues to inject its one publisher with live activity.
- Chat/daemon/boundary focused suite: 259 passed. Post-publisher-ownership
  `uv run --locked pytest -q`: 2456 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Every `ApplicationGraph` field has a current production use case.
  `DaemonState.application` remains the authority graph used by recurring
  scans and observation writes, while its publisher is shared by Chat,
  scheduler, live activity, and follow-up diagnostics; private renaming would
  not remove an object or dependency.
- Data CLI handlers now obtain `DataAdminService` once per operation and pass
  it through resource resolution, validation, and mutation. Repeated
  application-runtime lookup and authority validation are gone.
- Data CLI/boundary focused suite: 63 passed. Post-service-reuse
  `uv run --locked pytest -q`: 2456 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Memory add/search, source delete/extract, system status, and REPL
  memory dispatch now each resolve the invocation application once and reuse
  its resource graph. A full CLI AST audit finds no handler with more than one
  application/conversation lookup.
- `compose_cli_conversation_store` remains justified by more than twenty
  production callers as the narrow conversation capability accessor; removing
  it would spread graph traversal rather than remove composition.
- CLI/REPL focused suite: 325 passed. Post-lookup cleanup
  `uv run --locked pytest -q`: 2456 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Persona create/delete/enable now resolve one application graph, reuse one
  prompt snapshot for handle selection, and pass the composed trace recorder
  into lifecycle observation. The internal multi-handle resolver is no longer
  a pseudo-public CLI helper.
- Persona/CLI/observability focused suite: 334 passed. Post-persona-reuse
  `uv run --locked pytest -q`: 2456 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Memory candidate list/show/accept/reject/edit/merge now share one repository
  between handle resolution and mutation. Memory add/import/candidate tracing
  receives the already-composed recorder instead of reopening the CLI graph.
- Memory/CLI/observability focused suite: 329 passed. Post-capability-reuse
  `uv run --locked pytest -q`: 2456 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Memory source show/delete/chunks/extract and profile show/delete now pass one
  repository through handle resolution and execution. The profile-only
  repository pass-through helper is gone. Symbolic graph handlers already
  performed exactly one lookup each and remain unchanged.
- Memory source/profile focused suite: 320 passed. Post-repository-reuse
  `uv run --locked pytest -q`: 2456 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Notification show/send/dismiss now share one outbox between handle resolution
  and execution; send also reuses the same graph's runtime paths. Reason
  advance reuses one graph for its service and model-backed advancer.
- Reflection and trace helpers already perform one service lookup per handler;
  their shared accessors remain justified and unchanged.
- Notification/Reason focused suite: 660 passed. Post-lookup cleanup
  `uv run --locked pytest -q`: 2456 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Daemon lifecycle/request methods and ApplicationRuntime lazy ownership,
  closure, context binding, and worker propagation all have production
  consumers. ApplicationGraph raw resources remain required by specialized
  application composition rather than external domain adapters.
- `MemoryService.search_sources` and `search_profiles` had no production
  consumer beyond `pack()` and no documented external contract; both are now
  private packing steps. Reason workspace-path access and generic Trace
  record/link remain explicit, independently tested domain capabilities.
- Memory/Chat/agent focused suite: 192 passed. Post-service-surface cleanup
  `uv run --locked pytest -q`: 2456 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Every `MemoryRepositories` and `TraceServices` field has a production
  consumer; neither immutable resource bundle contains a historical field.
- `ApplicationRuntime` graph access, close, and enter critical sections never
  nest and expose no recursive callback. Its lifecycle mutex is now a plain
  `Lock`; concurrent first access still composes and returns exactly one graph.
- Application/CLI/REPL/daemon lifecycle focused suite: 56 passed; concurrent
  runtime suite: 6 passed. Post-lock cleanup `uv run --locked pytest -q`:
  2457 passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- EventPublisher, HandlerRegistry, DefinitionRegistry, component-log append,
  PersonaPromptRepository, and TraceRepository now use ordinary locks. Their
  callbacks/handlers run outside critical sections and their repository writes
  never nest.
- SQLite transaction/collection calls and Reason batch-write/save calls retain
  the only two `RLock` instances because both intentionally reacquire the same
  mutex within one atomic operation.
- Registry/event/log/repository focused suite: 208 passed. Post-lock audit
  `uv run --locked pytest -q`: 2457 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- The scheduler no longer mirrors running work in both an integer counter and
  its busy-resource set. Capacity, shutdown completion, and health now derive
  from the resource set that already owns serialization.
- The activity broker condition remains necessary for bounded cross-request
  long polling, while the daemon shutdown event is the one signal shared by
  process signals, the shutdown request, cleanup, and the server loop; neither
  duplicates scheduler lifecycle state.
- Scheduler/activity/server focused suite: 50 passed.
- Post-scheduler-state cleanup `uv run --locked pytest -q`: 2457 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- The daemon's `echo` request had no production client, CLI, or domain use case;
  it existed only as a transport test hook. It is gone from the wire request
  catalog and sealed handler registry, and framing tests now use the real
  `ping` request type.
- Protocol/request/transport focused suite: 115 passed. Post-request-surface
  cleanup `uv run --locked pytest -q`: 2456 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- `ReasonService.workspace_paths()` and `workspace()` had no production
  consumer and exposed infrastructure as if it were a reasoning use case.
  They and their private cache are gone; advancers and exports continue to
  receive the application-owned `reason_workspace` capability directly.
- Reason service/output/application-boundary focused suite: 117 passed.
- Post-Reason-service cleanup `uv run --locked pytest -q`: 2455 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Every ReflectionService and TraceQueryService method has a production CLI,
  REPL, agent, or scheduler consumer and remains public. TraceRecorder's generic
  `record()` and `link()` were used only by its own typed methods and test data
  setup, so they are now private construction/persistence helpers.
- Trace/reflection/CLI/Chat/boundary focused suite: 509 passed.
- Post-trace-service cleanup `uv run --locked pytest -q`: 2455 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Notification outbox/delivery and ConversationStore methods all have
  production state-machine or user-operation consumers. The standalone
  `empty_conversation_messages()` helper had one default-factory reference and
  is replaced by the built-in `list` factory.
- Conversation/notification focused suite: 77 passed. Post-helper cleanup
  `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Application composition helpers remain justified by distinct authority,
  projection, model, or surface-adapter boundaries. The apparent repeated
  `_optional_non_blank_string` definitions are two overload signatures and one
  implementation, so they remain intact.
- Protocol `empty_payload()` and runtime-job `_empty_job_data()` were pure
  single-use `{}` factories; typed `dict[...]` factories now provide the same
  isolation and stronger direct field typing without extra symbols.
- Protocol/runtime-message/payload/transport focused suite: 152 passed.
  Post-factory cleanup `uv run --locked pytest -q`: 2455 passed; Pyright:
  0 errors, 0 warnings; sdist and wheel build succeeded.
- Fifteen additional empty-container helpers across memory, profile, source,
  trace, notification, interactive-session, repository-stat, and reason-output
  models had no caller beyond dataclass/Pydantic defaults. Parameterized
  built-ins now express those exact types directly; ID/time and semantic
  factories remain named.
- Affected memory/profile/trace/notification/reason/session focused suite:
  604 passed. Post-domain-factory cleanup `uv run --locked pytest -q`: 2455
  passed; Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `EntrypointController._status_or_report()` only forwarded four same-class
  calls to `observe_daemon_status()` and added no contract or seam. Those paths
  now call the existing shared observation/error-rendering boundary directly.
- CLI/readiness focused suite: 327 passed; EntrypointController suite: 6
  passed. Post-pass-through cleanup `uv run --locked pytest -q`: 2455 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Remaining visible one-line adapter calls retain concrete contracts:
  daemon-status observation translates lifecycle errors, data resolution
  enforces internal visibility, and activity opening owns optional transport
  degradation. They are not pass-throughs and remain intact.
- Start and stop failure formatters had identical implementations and callers
  required only the common safe lifecycle message. One union-typed formatter
  now serves command, default-entrypoint, and interactive restart surfaces;
  observed start/stop/restart audit paths remain distinct.
- Lifecycle/CLI/entrypoint focused suite: 384 passed. Post-formatter cleanup
  `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Chat domain and daemon response previously carried the same generated text as
  both `answer` and `reply`. `ChatResult.reply`, the duplicate wire field, and
  their mapping are gone. The CLI explicitly projects wire `answer` into its
  presentation-only `InteractiveChatResult.reply` field.
- Scheduler-health mapping remains at the request handler because it is the
  sole boundary between the scheduler model and strict wire codec; moving it
  into either model would add a dependency rather than consolidate repetition.
- Chat/daemon/CLI focused suite: 465 passed. Post-DTO cleanup
  `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `ReasonRepository.project_root` had no production consumer; only the test
  convenience service used it to reverse-engineer composition from an injected
  repository. The property is removed and test composition now requires its
  authority root explicitly.
- Reason/Reflection/Chat/CLI focused suite: 658 passed. Post-repository-surface
  cleanup `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- `PrivateWorkspaceStore.scope` and `.database` had no production or test
  consumer. Owner paths remain the explicit workspace capability, so both
  properties and the mirrored `_scope` field are removed.
- Workspace/Reason/agent/Chat focused suite: 340 passed. Post-workspace-surface
  cleanup `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- Every `ConversationResources`, `ToolResources`, `ApplicationGraph`,
  `MemoryRepositories`, and `TraceServices` field has a production consumer.
  They remain explicit capability bundles rather than becoming service-locator
  lookups.
- `ConversationGraphRuntime._tools` mirrored the exact dictionary already owned
  by `ConversationToolRuntime`. Response composition uses one local reference
  and capability snapshots now read the sole catalog directly.
- Chat/agent/daemon/boundary focused suite: 367 passed. Post-tool-catalog
  cleanup `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- `ConversationGraphRuntime._memory_query_service` was read only during its own
  constructor. One local reference now injects the same MemoryService identity
  into context and persona components without retaining a third owner.
- Post-memory-service cleanup `uv run --locked pytest -q`: 2455 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `DataAdminService` no longer builds two per-instance indexes over its fixed
  16-item resource catalog. Name and collection aliases resolve directly from
  the sole catalog; exact storage-schema coverage validation remains intact.
- Data/application/boundary focused suite: 64 passed. Post-admin-index cleanup
  `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `DaemonState._schedule_periodic()` only wrapped scheduler submission for its
  sole startup caller. Startup now submits the immutable periodic catalog
  directly; focused tests exercise the real scheduler API instead of that
  production-private test seam.
- Daemon/boundary focused suite: 226 passed. Post-periodic-pass-through cleanup
  `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Socket `RequestHandler._daemon_state()` was a single-use state accessor whose
  only policy was a server-type check. Dispatch now performs that check where
  state crosses into request handling; transport tests use a real server shell
  instead of injecting the removed private seam.
- Socket/transport/request focused suite: 80 passed. Post-state-accessor cleanup
  `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- The one-shot Chat adapter's `_run_after_reply()` only performed one optional
  callback check for its adjacent caller. That check is now direct; the actual
  compression callback remains separate because it owns failure isolation and
  audit reporting.
- CLI/Chat focused suite: 511 passed. Post-callback cleanup
  `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- REPL `_reason_service()` had one caller and only traversed the application
  graph. The command now resolves the graph-owned ReasonService once directly;
  the helper and its otherwise-unused type import are gone.
- REPL/Reason/CLI/boundary focused suite: 702 passed. Post-accessor cleanup
  `uv run --locked pytest -q`: 2455 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `ReflectionScheduler._read_last_reflection()` had no production caller and
  existed only for direct private-method tests. It is gone; persistence checks
  assert the actual schedule record, while existing scheduling tests cover
  missing and corrupt state through the fail-closed production path.
- Reflection focused suite: 105 passed. Post-test-seam cleanup
  `uv run --locked pytest -q`: 2452 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `ConversationGraphRuntime.compression_node()` was absent from the production
  turn pipeline and called only by one node-contract test. Removing it also
  exposed `ConversationStateManager.compress()` as dead adaptation; both are
  gone. Durable background compression still uses the atomic
  `compress_conversation()` path.
- Chat/daemon/conversation focused suite: 351 passed. Post-compression-node
  cleanup `uv run --locked pytest -q`: 2452 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- `ChatResult.to_payload()` had no production or documented consumer; its only
  caller tested the obsolete generic mapping itself. It is gone. Daemon wire
  serialization remains solely owned by strict `ChatResponsePayload`, while
  CLI projection remains explicit.
- Chat/daemon/CLI focused suite: 246 passed. Post-result-serializer cleanup
  `uv run --locked pytest -q`: 2451 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `ReplCommandDispatcher.registered_commands` exposed its internal registry to
  one redundant test. It is gone; production construction already seals the
  registry with `expected_keys=command_names()`, and the mismatch failure test
  remains.
- REPL/handler/boundary focused suite: 135 passed. Post-introspection cleanup
  `uv run --locked pytest -q`: 2450 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `DaemonSignalOwner.installed` and `.owned_signals` were test-only views, and
  `_installed` duplicated the authoritative ownership map. All three are gone;
  install idempotence now derives from owning both signals, while partial
  ownership still fails closed and remains retryable.
- Signal/daemon-lifecycle focused suite: 28 passed. Post-signal-state cleanup
  `uv run --locked pytest -q`: 2450 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `DaemonInstanceLock.acquired` and `MemoryCuratorPlanLock.acquired` projected
  private handle presence solely for tests. Both are gone; tests retain real
  contention, release/reacquisition, context cleanup, and combined failure
  coverage without exposing lock internals.
- Daemon-instance/memory-plan lock focused suite: 28 passed. Post-lock-view
  cleanup `uv run --locked pytest -q`: 2450 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- `HandlerRegistry.sealed` was read only by tests. It is gone; unsealed
  dispatch, post-seal mutation/resolution, and incomplete/extra catalogs remain
  executable errors. The composable `handler()` decorator is retained.
- Handler/daemon-request/REPL focused suite: 31 passed. Post-sealed-view cleanup
  `uv run --locked pytest -q`: 2449 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `HandlerRegistry.registered_keys` existed for tests plus one daemon guard.
  The guard repeated guarantees already enforced by the strict RequestType
  codec and exact sealed request catalog. Both the projection and unreachable
  guard are gone; registry dispatch retains its own unknown-key error.
- Handler/daemon-request/transport focused suite: 94 passed. Post-key-view
  cleanup `uv run --locked pytest -q`: 2447 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- The entire `nuself.authority` module was legacy: `get_authority_root()` had no
  caller and `ensure_authority_root()` was called only by its own test. It and
  that test are gone; scope resolution plus `scope init` remain the sole
  managed-authority initialization path.
- Scope/config/lifecycle focused suite: 94 passed. Post-authority-module cleanup
  `uv run --locked pytest -q`: 2446 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `render_reason_step_detail()` was called only by one test and duplicated the
  default behavior of production `render_step_watch_entry()`. It is gone; the
  terminal-status assertion now exercises the live watch renderer.
- TUI/Reason/CLI focused suite: 600 passed. Post-renderer cleanup
  `uv run --locked pytest -q`: 2446 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `render_host_decision()` produced a second format and was called only by its
  own test. It is gone; production `render_log_event()` remains the sole host-
  decision path and already covers escalation metadata without repetition.
  The LLM specification now describes that actual shared renderer.
- TUI/persona/Chat focused suite: 335 passed. Post-host-renderer cleanup
  `uv run --locked pytest -q`: 2445 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `render_agent_skill_sections()` belonged to the retired eager skill-prompt
  path and was called only by two tests. It is gone; production keeps the lazy
  `load_skill` tool, placeholder expansion, and exact skill-to-tool mapping.
- Agent/Chat/boundary focused suite: 335 passed. Post-eager-skill cleanup
  `uv run --locked pytest -q`: 2443 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `build_workspace_tools()` only wrapped one concrete workspace in a lambda and
  was called exclusively by tests. It is gone; production and tests now use
  `build_workspace_tools_from_provider()` as the sole lazy, thread-aware
  composition path.
- Agent/Reason/workspace/boundary focused suite: 100 passed. Post-workspace-
  builder cleanup `uv run --locked pytest -q`: 2443 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- `read_stream_frame()` and `BinaryFrameReader` were test-only alternatives to
  the production socket reader and could not reject buffered trailing frames.
  They are gone; client and server share one bounded `read_socket_frame()` path,
  while response writes retain partial-write-safe stream handling.
- Daemon transport/server/request focused suite: 77 passed. Post-stream-reader
  cleanup `uv run --locked pytest -q`: 2443 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.

- Memory, reason, persona, notification, reflection, Chat, endpoint, storage,
  and observability audit validators now compose the shared exact-field
  primitive; their registries and semantic value checks remain domain-owned.
- Daemon start/stop lifecycle projection shares one transition metadata
  builder; client/lifecycle protocol and state APIs were retained only after
  confirming current CLI/REPL production callers.
- Focused affected-domain suite: 325 passed.
- `uv run --locked pytest -q`: 2447 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- Registered daemon, storage, endpoint, Chat, memory, notification, persona,
  reason, reflection, and observability failure producers now share one narrow
  interpreter for diagnostic derivation, definition validation, and sink
  invocation; event/message/metadata selection remains domain-owned.
- Registered-failure focused suite: 272 passed; endpoint failover integration:
  45 passed.
- Post-interpreter `uv run --locked pytest -q`: 2447 passed; Pyright remains
  0 errors and 0 warnings.
- `ApplicationRuntime` no longer mirrors the backend cache or exposes unused
  opened/closed flags; its behavioral laziness, reuse, idempotent close, and
  post-close rejection remain tested.
- CLI uses the sole application runtime context directly; the pass-through
  `use_cli_application_runtime` alias is gone while authority-drift validation
  remains in CLI composition.
- Daemon server injects `ApplicationGraph` into `DaemonState`; state no longer
  discovers, creates, or retains an `ApplicationRuntime`.
- Composition/lifecycle focused suite: 62 passed.
- Post-ownership `uv run --locked pytest -q`: 2448 passed; Pyright remains
  0 errors and 0 warnings.
- `ApplicationGraph` now composes one authority-scoped memory query, reason,
  and reflection service; Chat, CLI, REPL, and daemon consumers reuse them.
- Removed the repeated reason/reflection service factories; a model-backed
  reason advancer is a one-operation method input rather than a parallel
  service graph.
- Post-service-composition `uv run --locked pytest -q`: 2448 passed;
  `uv run --locked pyright`: 0 errors, 0 warnings; `uv build`: sdist and wheel
  succeeded.
- Daemon request-handler state no longer exposes the conversation runtime that
  no registered request handler uses; domain runtime ownership remains inside
  daemon composition.
- Five recurring submissions now derive from one immutable task/interval list;
  four mutable interval mirror fields and repeated startup branches are gone.
- Replaced obsolete named-factory boundary checks with stronger application
  package boundaries after those factories were deleted.
- Daemon/boundary focused suite: 221 passed. Post-periodic-composition
  `uv run --locked pytest -q`: 2448 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Daemon protocol/payload codecs remain intentionally distinct: each represents
  a different exact wire schema and classified decode context; no generic codec
  layer was introduced.
- Reason export now receives workspace, output service, and scheduler sink as
  complete construction dependencies. Removed nullable dependency mirrors,
  `prepare()`, late sink binding, and their runtime guards.
- Reason-export focused suite: 91 passed. Post-export-composition
  `uv run --locked pytest -q`: 2448 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Lifecycle start/stop/restart result types remain justified by their distinct
  transition and audit consumers. `DaemonStopError` no longer mirrors an
  independently supplied ownership value; it derives ownership from its sole
  authoritative status snapshot.
- Lifecycle/CLI focused suite: 444 passed. Post-lifecycle-state
  `uv run --locked pytest -q`: 2448 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Activity broker, wire codecs, and REPL fallback remain separate because they
  own bounded fan-out, protocol validation, and durable recovery respectively.
  Removed four historical underscore lifecycle aliases from live visibility;
  only registered dotted runtime identities and current audits remain.
- Activity-only close and event-classification helpers are now private module
  details instead of implied cross-module APIs.
- Activity/client focused suite: 120 passed. Post-activity cleanup
  `uv run --locked pytest -q`: 2449 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Scheduler task, completion, active identity, and busy-resource state remain
  necessary for coalescing and serialization. Four lifecycle booleans were
  replaced by one monotonic `created/running/stopping/stopped` phase; running
  and accepting health now derive from that source.
- Scheduler/daemon focused suite: 50 passed. Post-scheduler-lifecycle
  `uv run --locked pytest -q`: 2449 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Daemon server keeps named exhaustive cleanup because ordinary context-manager
  unwinding cannot retain and report every failure. Removed the pass-through
  scheduler readiness method; the process owner now checks the injected
  scheduler and pre-readiness shutdown directly.
- Replaced the daemon lifecycle test fixture's obsolete five-worker model with
  the production single-scheduler boundary. The private owned runner no longer
  returns a constant exit code; `run_daemon()` alone owns process status.
- Server lifecycle focused suite: 98 passed. Post-server-composition
  `uv run --locked pytest -q`: 2449 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `DataAdminService` generic list/get remain justified by the explicit
  user-maintenance contract; editability, codecs, identity, and internal
  visibility stay enforced at that boundary.
- Trace CLI show, links, and derived-index rebuilding now use
  `TraceQueryService`. `TraceServices` and the trace package no longer expose
  `TraceRepository`; recorder and query still share one composed repository.
- Trace service/CLI focused suite: 14 passed. Post-trace-boundary
  `uv run --locked pytest -q`: 2449 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Reason scheduling now persists cooldown through the existing complete
  `ReasonService`; its repository property, scheduler repository dependency,
  and manual thread reconstruction are gone. `ApplicationGraph` no longer
  exposes the Reason repository to process adapters.
- Reflection CLI, REPL, and agent tools now use the existing
  `ReflectionService` for browse, status, organization, and promotion use
  cases. The daemon reuses that service as its organizer capability while
  candidate and relevance workflows retain their explicit domain repository.
- Reason/Reflection boundary suite: 1012 passed. Post-boundary
  `uv run --locked pytest -q`: 2449 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- The former query-only memory helper is now the complete user-facing
  `MemoryService`: search, context packing, filtered count, archive, and
  importance mutation share one composed repository and authority boundary.
- Agent tools now receive only `MemoryService`; the parallel entry-repository
  capability and duplicated save mutations are gone. Curator, source,
  projection, repair, and migration workflows retain explicit repositories
  instead of being forced through a universal memory facade.
- Memory/chat focused suite: 98 passed. Post-memory-service
  `uv run --locked pytest -q`: 2449 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- The first full run exposed an unrelated concurrent legacy-layout migration
  race between directory enumeration and `lstat`; its isolated rerun passed,
  so the next phase will remove the check/use window explicitly.
- Legacy-layout validation and copying now share one transient-file predicate.
  Runtime locks and SQLite WAL/SHM/journal files are skipped before `lstat`, so
  normal SQLite checkpoint cleanup cannot race source validation; committed WAL
  state remains captured through SQLite backup.
- Layout migration suite: 8 passed; the concurrent publication case passed
  three additional consecutive process runs. Post-race-fix
  `uv run --locked pytest -q`: 2449 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `ApplicationGraph` now composes one Reason workspace store and reuses it for
  the Reason service, Chat tools, model-backed advancement, and daemon export;
  three equivalent authority-scoped adapter constructions are gone.
- Conversation store/history remain distinct write/read capabilities;
  NotificationOutbox is already the complete notification API; persona prompt
  persistence and reflection repository/schedule state remain confined to
  application-owned composition. No facade or resource-bundle layer was added.
- Reason/application focused suite: 532 passed. Post-workspace-reuse
  `uv run --locked pytest -q`: 2449 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `ApplicationGraph` now owns one immutable configuration snapshot. Chat,
  daemon scheduling, notification adapter composition, endpoint construction,
  and Reason export language policy reuse it; explicit config inspection and
  documented per-operation adapter reloads remain independent.
- `ConversationGraphRuntime` no longer discovers settings or endpoints from a
  project root. Both are required construction inputs, and its obsolete
  `ChatAgentSettings.from_project` composition shortcut is gone.
- Chat persona tools reuse the same resolved endpoint tuple as response and
  compression components instead of constructing a second configured model
  set. Reason export planner/runner receive language preference explicitly.
- Config/Chat/daemon focused suite: 524 passed. Post-config-snapshot
  `uv run --locked pytest -q`: 2449 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- One daemon startup now resolves and state-orders configured endpoints exactly
  once, then supplies the tuple to Chat, memory curation, reflection candidate
  and relevance agents, persona discussion, Reason advancement, and export.
  Component-specific wrappers and audit identities remain independent.
- Added a daemon composition regression proving one endpoint resolution instead
  of the previous six. Removed the production-unused default Persona graph
  factory and the pass-through combined Memory tool builder.
- Endpoint/agent focused suite: 679 passed. Post-endpoint-reuse
  `uv run --locked pytest -q`: 2450 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Persona tool builders and Reason export now require an explicit `TextAgent`;
  the global `default_text_agent` shortcut is gone. Reason persona tools build
  their component-tagged wrapper from the advancer's existing endpoints.
- Removed unused Persona prompt/tool/default-discussion re-exports from the
  package facade. `agent.tools.__init__` is now import-light; Chat aggregation
  lives in `agent.tools.composition`, and domain users import workspace tools
  directly.
- The import-light package boundary fixes a real `reason.output` ↔ agent-tools
  initialization cycle exposed by multiprocessing spawn. The three failing
  cross-process SQLite tests and a 691-test affected suite pass afterward.
- Post-fallback/package cleanup `uv run --locked pytest -q`: 2450 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Memory intake, curation, and optimization now require an injected typed
  `StructuredAgent`. CLI/application composition builds those agents from the
  active configuration snapshot and resolved endpoints; domain constructors no
  longer discover configuration or models.
- Remaining configured structured-agent fallbacks are retained only for Reason
  prompt and standalone Reflection/Persona entry points that have real direct
  callers. Memory/CLI/daemon focused suite: 687 passed.
- Post-memory-agent-boundary `uv run --locked pytest -q`: 2450 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- `nuself.reason` is now an import-light domain namespace instead of a facade
  that eagerly initialized advancer/model code, repository, output, scheduler,
  service, and store aliases. The daemon imports its scheduler from the owning
  module, and an executable boundary test prevents root imports from returning.
- Reason/daemon/boundary focused suite: 351 passed. Post-Reason-package cleanup
  `uv run --locked pytest -q`: 2451 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `nuself.persona` is now an import-light namespace instead of eagerly joining
  definitions, model-backed graph orchestration, and competitive discussion.
  Production and test consumers import owning modules directly.
- Reflection scheduling no longer imports the concrete Persona result merely
  for typing; its narrow read-only result protocol makes the existing injected
  discussion capability a real consumer-owned boundary.
- Persona/Chat/Reflection/boundary focused suite: 488 passed. Post-Persona
  cleanup `uv run --locked pytest -q`: 2451 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- `nuself.reflection` is now an import-light namespace; its previous candidate,
  relevance, scheduler, repository, organizer, and service aggregation had no
  production consumer. Tests now name the modules whose behavior they verify.
- Reflection/boundary focused suite: 159 passed. Post-Reflection cleanup
  `uv run --locked pytest -q`: 2451 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Profile's unused package facade and Trace's domain/repository/service facade
  are gone. The Trace CLI now imports only its repository-owned error and
  visibility filter, while tests name their domain and service modules.
- Trace/Profile/CLI/boundary focused suite: 394 passed. Post-facade cleanup
  `uv run --locked pytest -q`: 2451 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- The 129-line `nuself.runtime` facade is now an import-light namespace.
  Production code and migration scripts import serialization from `messages`
  and execution scope from `context`; event/job tests use their owning modules.
  Importing one codec no longer initializes cleanup, registries, handlers,
  events, jobs, diagnostics, and execution infrastructure transitively.
- Runtime/infrastructure focused suite: 305 passed. Post-Runtime cleanup
  `uv run --locked pytest -q`: 2451 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `nuself.agent.chat` is now an import-light namespace. Application composition
  imports the runtime and DTOs from their owning modules; daemon and evaluation
  depend only on result types. Conversation storage, resource snapshots,
  response services, capabilities, and the full graph are no longer leaked or
  eagerly initialized by the package root.
- Chat/daemon/evaluation/boundary focused suite: 286 passed. Post-Chat cleanup
  `uv run --locked pytest -q`: 2451 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- The Application package root no longer re-exports Trace composition; process
  and test consumers import `application.trace` directly. The Decorators root
  remains intentionally because it is the cohesive, widely consumed public
  spelling for inert orthogonal feature declarations.
- Corrected the agent-tool specification: its package root is import-light and
  Chat aggregation belongs only to `agent.tools.composition`, matching code.
- Application/trace/boundary focused suite: 137 passed. Post-package-root audit
  `uv run --locked pytest -q`: 2451 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Notification implementation moved from the package root to its owning
  `outbox` module; the root is import-light and the former bottom-of-file
  delivery re-export/circular initialization path is gone.
- Adapter contract and log adapter now live in `notification.adapters`, while
  delivery orchestration imports adapter and outbox capabilities directly.
  Email/macOS adapters, composition, CLI, daemon, tests, and evaluation use
  their owning modules rather than a forwarding facade.
- Reflection scheduling no longer imports or constructs `OutboxEntry`; it calls
  the outbox's use-case-level `enqueue` capability through its consumer-owned
  publisher protocol.
- Notification/Reflection/daemon/boundary focused suite: 220 passed.
  Post-Notification-boundary `uv run --locked pytest -q`: 2451 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Notification records and strict codecs now live in the dependency-light
  `notification.model`; the persistent repository and cross-process entry lock
  remain together in `notification.outbox`. Email, macOS, TUI, delivery, and
  adapter code no longer load storage or `fcntl` merely to inspect an entry.
- Model/outbox focused suite: 220 passed. Post-model separation
  `uv run --locked pytest -q`: 2451 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- CLI root no longer re-exports four Reflection handlers or private REPL
  completer/transcript helpers solely for tests. Tests import each owning
  command or REPL module directly.
- Removed the unused memory-preview constant and duplicate chat-timeout
  constant; `ChatConfig.request_timeout_seconds` remains the sole default.
- CLI/REPL/Reflection focused suite: 532 passed. Post-CLI-surface cleanup
  `uv run --locked pytest -q`: 2451 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Interactive callback composition now belongs to `cli.repl.composition`, and
  shared chat reply/banner rendering belongs to `cli.presentation`. The CLI
  root retains the sole application-runtime lifecycle plus parser and Chat
  adapter binding; it fell from 349 to 194 lines.
- Interrupt cancellation, daemon activity transport, log fallback, transcript
  capture, curation, startup notices, and session headers retain their existing
  paths through the moved callback graph.
- CLI/REPL focused suite: 574 passed. Post-REPL-composition
  `uv run --locked pytest -q`: 2451 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- The REPL registry's command taxonomy and dispatcher handler table remain
  separate by design: metadata drives aliases/help/completion, while the sealed
  handler registry proves exact execution coverage without importing runtime
  handlers into metadata. Removed the test-only `command_matches` query.
- Reason step watching now lives in `cli.reason_watch`, shared directly by the
  argparse adapter and REPL dispatcher. The top-level parser no longer imports
  `cli.repl.commands` for a one-shot handler, and REPL commands no longer own
  the argparse Reason watch adapter.
- CLI/REPL/Reason focused suite: 838 passed. Post-watch-boundary
  `uv run --locked pytest -q`: 2451 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Persona lookup, confirmation, mutation feedback, and lifecycle trace now use
  parameterized `cli.persona_management` workflows shared by terminal surfaces.
  Argparse handlers only unpack namespaces; REPL passes parsed values directly
  and no longer imports argparse or one-shot Persona handlers.
- Added executable boundaries prohibiting parser→REPL command imports,
  argparse inside REPL commands, and REPL→Persona command-adapter imports.
- Persona/CLI/REPL/boundary focused suite: 776 passed. Post-Persona-boundary
  `uv run --locked pytest -q`: 2452 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Compact memory preview querying/rendering now belongs to
  `cli.memory_preview`, shared by one-shot and REPL surfaces without importing
  a memory command adapter.
- Shared ANSI output and visible-handle resolution moved from
  `cli.commands.output` to `cli.output`; REPL now imports no one-shot command
  module at all.
- CLI/REPL/Memory focused suite: 768 passed. Post-REPL-adapter cleanup
  `uv run --locked pytest -q`: 2452 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `DaemonScheduler.submit()` now returns its completion `Future` directly.
  Duplicate identities return the same handle, so coalescing remains explicit
  without a production-unused admission label or submission wrapper.
- Scheduler/daemon focused suite: 47 passed. Post-submission-wrapper cleanup
  `uv run --locked pytest -q`: 2443 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Reason-export manifest inspection, failure persistence, and manifest decoding
  are private daemon steps rather than implied public APIs. Inspection carries
  only terminal state/chunk diagnostics, and failure persistence returns only
  the attempt count its sole consumer needs; the durable manifest remains the
  authority for recovery.
- Reason-export focused suite: 24 passed. Post-export-result narrowing
  `uv run --locked pytest -q`: 2443 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- Ping success now carries only its non-blank `authority_id`; request type and
  successful response status already express `pong`. The client still rejects
  another authority and exact decoding rejects the removed field.
- Daemon payload/transport/server/lifecycle focused suite: 144 passed.
  Post-ping-payload cleanup `uv run --locked pytest -q`: 2444 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Empty daemon requests and responses now share one exact `EmptyPayload` codec.
  Shutdown success returns `{}` and the fixed response-only `MessagePayload`
  plus client string comparison are gone; the separate shutdown audit message
  remains user-facing observability.
- Daemon payload/transport/server/lifecycle focused suite: 144 passed.
  Post-shutdown-payload cleanup `uv run --locked pytest -q`: 2444 passed;
  Pyright: 0 errors, 0 warnings; sdist and wheel build succeeded.
- Idempotent activity close now uses the shared exact empty response. The
  production-unread `ActivityCloseResponsePayload` and client boolean return
  are gone; `ActivityBroker.close()` still owns and tests actual deletion while
  REPL cleanup remains best effort on every exit path.
- Activity/payload/transport/REPL focused suite: 89 passed. Post-close-response
  cleanup `uv run --locked pytest -q`: 2444 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- Daemon health now returns `SchedulerHealthPayload` directly. The removed
  `HealthResponsePayload` only nested that sole scheduler under one field, and
  its only production consumer immediately unwrapped it; all six health fields
  and CLI presentation remain unchanged.
- Payload/server/client/CLI focused suite: 407 passed. Post-health-wrapper
  cleanup `uv run --locked pytest -q`: 2444 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- Activity open response and close request now share one exact
  `ActivitySubscriptionPayload`; the two prior classes duplicated the same
  non-blank `subscription_id` codec. Next-batch request remains separate because
  its timeout and limit are independent inputs.
- Activity/payload/transport/REPL focused suite: 89 passed. Post-subscription-
  codec cleanup `uv run --locked pytest -q`: 2444 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.
- Reason-export inspection now exists only for pending work. Terminal manifests
  return no inspection instead of allocating an object with a mirrored
  `terminal` flag; pending results contain only chunk diagnostics consumed by
  composition.
- Reason-export focused suite: 24 passed. Post-pending-inspection cleanup
  `uv run --locked pytest -q`: 2444 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- One-shot and REPL restart adapters now each catch start/stop failures through
  one identical presentation branch. The distinct lifecycle exception classes,
  restart audit stages, and failure metadata remain owned by lifecycle
  orchestration.
- CLI/lifecycle focused suite: 377 passed. Post-restart-branch cleanup
  `uv run --locked pytest -q`: 2444 passed; Pyright: 0 errors, 0 warnings;
  sdist and wheel build succeeded.
- `DataAdminService.validate()` now returns no decoded domain model. Every
  production caller used it only as a validation command; invalid records still
  raise through the owning memory/conversation codec, while update validates
  again at the mutation boundary.
- Application/data focused check plus full type gate passed. Post-validation-
  result cleanup `uv run --locked pytest -q`: 2444 passed; Pyright: 0 errors,
  0 warnings; sdist and wheel build succeeded.

## Last Completed Goal

Simplified composable daemon audit infrastructure without merging domain
registries or changing protocol, storage, scheduler, or CLI behavior.

## Completion Evidence

- Removed the production-unused worker-timeout event, reporter, schema, and
  tests left by the former multi-worker daemon.
- Removed the constant `memory_curation_requested` chat audit field; durable
  recovery remains authoritative.
- Daemon audit domains now compose one exact-field validation primitive while
  retaining independent event definitions and producers.
- Focused daemon/shared audit suite: 71 passed.
- `uv run --locked pytest -q`: 2447 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- `uv build`: `nuself-0.3.1` sdist and wheel built successfully.
