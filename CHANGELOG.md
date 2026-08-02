# Changelog

All notable user-visible changes to NuSelf are tracked here.

This project follows the versioning rules in [`docs/spec/versioning.md`](docs/spec/versioning.md).

## Unreleased

- Application composition now loads configuration from its already-resolved
  scope, preserving user defaults beneath workspace overrides.
- Daemon request state and its socket adapter now expose the selected
  `authority_root` explicitly instead of calling it a project root.
- `RuntimePaths` now exposes only the canonical `authority_root`; removed its
  temporary legacy `project_root` alias and migrated all typed-path consumers.
- System health now branches directly on the daemon status observation instead
  of maintaining a duplicate unavailable flag.
- The daemon-list handler now owns its fixed two-line rendering directly,
  removing a single-use public formatter.
- CLI lifecycle failures now use the shared safe diagnostic formatter directly,
  removing a policy-free lifecycle-specific forwarding function.
- Raw daemon request transport is now private to the typed client operations;
  low-level framing tests continue to exercise the internal boundary directly.
- Generic daemon response decoding is now private to the typed client
  operations; failure tests exercise the public health boundary instead.
- Daemon stop failures now expose ownership through their authoritative status
  snapshot only, removing a duplicate forwarding property.
- Daemon chat response confidence decoding now lives beside its range policy,
  removing a generic helper with one caller.
- Daemon chat request decoding now keeps its two optional ID defaults directly
  in the owning codec, removing a two-call overloaded helper.
- The log-only notification adapter now receives the resolved project path
  directly instead of retaining the wider runtime-path aggregate.
- Notification adapter composition now receives only validated email and macOS
  settings instead of the aggregate system configuration.
- macOS AppleScript escaping is now a private adapter implementation detail;
  tests verify exact quoting through the emitted subprocess command.
- The macOS notification adapter now keeps its construction-time executable
  availability private; tests control discovery rather than mutating public
  adapter state.
- The macOS notification adapter now requires a composition-resolved project
  path and no longer resolves authority through an optional constructor input.
- Notification idempotency lookup now lives directly inside transactional
  `add()`; removed its single-use private helper and moved concurrency-test
  instrumentation to the real list boundary.
- Notification outbox state transitions now expose their collection writes
  directly, removing a policy-free `_write_entry()` forwarding method.
- `ActivityBroker.close()` now matches the idempotent empty daemon response and
  returns no test-only removal boolean.
- Chat tool prompt rendering now lives directly in `ConversationToolRuntime`,
  removing its single-use module helper and iterable-only import.
- Chat prompt composition now checks its composed tool registry directly,
  removing the single-use `has_tool()` membership facade.
- Chat skill registration now computes its explicit tool intersection directly,
  removing a single-use policy-free projection helper and unused type import.
- Prompt-only advisory skills with an intentionally empty `allowed-tools`
  declaration remain available, while stale non-empty tool declarations stay
  filtered and receive no component-based fallback.
- Agent skills now receive only explicitly declared tools present in the
  runtime; removed component-based fallback that could mask a stale declaration
  and silently broaden a skill's tool authority.
- Chat now registers tools and advertises skills only for capabilities present
  in that runtime; direct chat without a daemon job sink no longer exposes the
  unusable Reason export tool or `reason_output` skill.
- Reason export planning now requires a concrete job sink per operation;
  surfaces without daemon scheduling fail before creating artifacts instead of
  reporting a job as queued without submitting it.
- Reason output persistence now writes manifests/progress directly in their
  owning flows and resolves one-call section/PDF branches in place, removing
  four policy-free internal forwarding helpers.
- Reason export composition now has one injected-runner path; removed the
  production-unused deterministic `compose_job()` renderer that could bypass
  the daemon's model-backed body composition policy.
- Reflection relevance now exposes only its complete score operation; removed
  an unused boolean facade that discarded the rest of the LLM decision.
- Reflection candidate generation no longer accepts the full reflection
  configuration it never consumed; schedule and relevance policy stay with
  their actual owners.
- Reason thread prompt generation is now an application-composed capability;
  the domain service no longer reloads model configuration, while provider
  clients remain lazy until a thread is actually started.
- Legacy v0.3.0 authority-layout migration now runs only from
  `scripts/migrate_legacy_layout.py`; removed the installed module and
  top-level `nuself migrate-layout` command.
- Configuration loading now accepts only the current strict schema; removed
  runtime mutation/warnings for `experimental.langmem_adapter` and the special
  v0.2.5 email migration error.
- Removed a one-helper Reason list alias and made Persona discussion reuse the
  existing identical non-blank text constraint from its domain dependency.
- Runtime context decoding now accepts only canonical `conversation_id` and
  rejects the pre-v0.3.1 chat `thread_id` alias.
- Configuration caching now relies solely on automatic path/mtime/size
  invalidation; removed an explicit reset method used only by one test.
- Removed the unused Profile statistics type/function; Memory statistics remain
  the only statistics API because they have an actual product consumer.
- Tool outcomes now use their validated dataclass constructor directly;
  removed success/failure convenience factories used only by tests.
- Reason output now exposes only its active plan/get/compose/path operations;
  removed test-only start/resume/list wrappers and obsolete cleanup for an
  export lock that the single-scheduler flow never creates.
- Removed an unused chat logger and a stale Reason storage-version declaration
  that did not participate in logging, decoding, or schema validation.
- The Reason repository no longer exposes a no-op `ensure()` or an unused raw
  step lookup; thread-scoped ordered step access remains the service boundary.
- Memory application composition no longer exposes unused type/relation
  registry overrides; custom registries remain available to focused repository
  construction.
- Raw Source document writes are now direct internal steps of complete source
  ingestion; CLI tests use real temporary files instead of a partial-write API.
- Source chunk replacement is now an internal part of the complete ingest
  operation instead of an independently exposed repository mutation.
- Memory relation listing now owns its one-shot projection and filtering,
  removing a single-use private projection method.
- Removed the unused Memory-object persistence adapter; memory entry writes now
  expose only the canonical validated `save(MemoryEntry)` repository boundary.
- Memory symbolic graph projection now has one `compute_graph()` implementation
  reused by repository operations and external query expansion, removing a
  private mirror and public pass-through.
- Reflection status decisions now remain in the user service and organizer;
  removed repository-level dismiss/archive use cases that re-read already
  resolved entries before saving them.
- Reflection persistence now uses one stable-ID `save()` operation, removing
  identical `add()` and `update()` repository APIs while retaining explicit
  status-transition operations.
- Reason pause, resume, resolve, and archive keep their explicit service API
  while their shared transition rule now owns ID-or-index resolution, removing
  four repeated adapter steps.
- Reason advancement now resolves one concrete step before mutation, removing
  repeated impossible null branches and a one-use optional-summary helper from
  state construction, persistence, and auditing.
- Reason service no longer retains an unused constructor-time advancer;
  advancement receives its narrow advancer or structured step explicitly at
  the operation boundary, removing two competing dependency sources.
- Reason scheduler composition now requires its advancer protocol capability,
  removing an unused missing-dependency mode that silently disabled background
  advancement at runtime.
- Reason output now owns one validated job-path operation reused by daemon
  execution, and submits export jobs directly at the sink boundary, removing
  private path pass-throughs, duplicate manifest assembly, and a one-call
  enqueue closure.
- Private workspace paths now expose only the distinct export root and
  authority database, removing an unused notes path and an artifacts alias of
  the root; artifact writers derive their owned child paths directly.
- Private workspace consumers now use the side-effect-free `paths()` resolver
  directly, removing a misleading `ensure()` alias that created nothing.
- Memory and profile statistics now use standard-library counting directly,
  removing two duplicate repository-local counting implementations.
- Notification delivery loops now validate and freeze their adapter index once
  at composition instead of rebuilding it for every poll and pending entry;
  the canonical adapter builder now returns its ordered plan as an immutable
  tuple.
- Reflection organizer composition now requires an explicit resolved project
  root so successful merge audits cannot silently lose authority scope.
- Reason scheduler composition now requires an explicit resolved project root,
  preventing background failure observations from silently losing authority
  scope.
- Background Reason scheduling now depends on the existing one-operation
  advancer protocol instead of the concrete model-backed implementation.
- Daemon durable follow-up admission no longer exposes an unused boolean
  result; deferral remains observable and recoverable through its existing
  typed boundary.
- Daemon reflection checks now call the scheduler's authoritative `reflect()`
  operation once instead of evaluating its jittered schedule gates twice.
- Conversation and notification resource locking now share one managed-file
  lock lifecycle primitive instead of maintaining duplicate stateful classes
  or repeating its parent-directory preparation at domain call sites.
- Visible tool-call leakage rejection now owns its sole marker check directly,
  removing a one-use substring-classifier helper.
- Unconfigured and exhausted-endpoint chat fallbacks now share one last-user-
  message extractor while retaining distinct cause text and epistemic policy.
- REPL memory search and reflection indentation now stay at their sole command
  branches, removing two one-use public helpers.
- Interactive reflection and notification pending/all views now share one
  domain handler each, replacing two duplicate public list handlers.
- Interactive Reason commands now name their ID/index inputs as Reason thread
  references instead of carrying misleading conversation terminology.
- Interactive memory entry, review-candidate, and source commands now use the
  shared visible-handle resolver instead of duplicating numeric index parsing.
- Trace CLI composition now borrows only the read-only query service instead of
  receiving the recorder-bearing trace service bundle.
- REPL exit curation now receives only the selected authority and scans pending
  memory observations, removing an ignored conversation-ID dependency.
- Authority ID generation now accepts only its canonical-root identity input,
  removing a discarded scope-kind parameter while preserving v1 IDs.
- Chat-persona lifecycle points now write their closed persona audits directly,
  removing three one-use forwarding methods and two discarded parameters.
- Reason workspace and persona tools now share one thread-scoped workspace
  resolver instead of duplicating authority and namespace composition.
- Reflection-promotion trace recording now persists its owned link directly,
  removing a one-use generic link pass-through from `TraceRecorder`.
- Trace, reflection, and Reason commands now use one shared JSONL output
  primitive instead of maintaining identical domain-local printers.
- Daemon state now borrows the authority-scoped application graph only during
  composition and retains explicit task capabilities instead of exposing the
  complete graph as a long-lived service locator.
- Memory record and payload decoding now share one required-string and one
  optional-string codec across dict and mapping inputs, replacing three
  duplicate validators.
- Atomic text and binary publication now share one internal path-fsync
  primitive instead of duplicate file and directory implementations; callers
  retain their distinct pre/post-replace failure contracts.
- The chat respond stage now calls its injected response service directly,
  removing two exact runtime pass-through methods while retaining separate
  completion and finalization operations.
- Reason output chunk lifecycle audits now share one exact thread/job/chunk
  metadata validator while retaining event-specific status, error, and duration
  policies.
- Memory curator and optimizer audits now use one sealed-domain
  `write_memory_audit()` operation instead of two identical writer façades.
- Memory curation now joins observation fragments and removes backend record
  identity directly at their sole consumption sites, eliminating two exact
  one-use helpers.
- Memory curator plan corruption now preserves its typed store error across the
  curator boundary instead of passing through a one-use generic rewrapper.
- Memory curator recovery and operator inspection now share the plan store's
  single typed `get()` operation. The duplicate `resumable()` read and
  standalone one-use observation-ID validator were removed.
- Visible-handle parsing now keeps selection-shape classification private and
  exposes only the shared parse/resolve operations used by command adapters.
- SQLite rollback-only and rollback-cleanup failures now remain distinct direct
  runtime errors without an unused transaction exception family.
- Handler registry duplicate, sealed, unsealed, coverage, and unknown-key
  failures now remain distinct direct runtime errors without an unused common
  exception family.
- Daemon requests now generate their default UUID-hex identity directly at the
  typed request field, removing an orphaned standalone generator API.
- Scheduler capacity and stopped-admission failures now remain distinct direct
  runtime errors without an unused common exception base.
- Daemon lifecycle cleanup now shuts down its sole scheduler directly. The
  state-level plural `stop_background_tasks` pass-through API was removed;
  startup still owns durable recovery and recurring task admission.
- Successful chat follow-up adapters now obtain committed-turn evidence through
  one `ChatResult` invariant. Direct CLI and daemon paths no longer maintain
  separate missing-turn validation branches; memory projection, curation, and
  compression ownership remain unchanged.
- Application storage lifetime is now owned directly by `ApplicationRuntime`.
  The process-global default-backend cache, lock, override/reset API, and
  aggregate reset error were removed; manual scripts and tests now use explicit
  scoped ownership and close their selected backends deterministically.
- Required Reason and memory-curation trace collaborators are now represented
  as non-null service dependencies, while retaining best-effort trace failure
  isolation. Daemon task construction now uses one path for captured and
  explicitly supplied runtime contexts.
- Initialized CLI and REPL domain handlers now enter through one
  authority-validating application composition API. The redundant
  conversation-store composition shortcut and its separate mock surface were
  removed; explicit backend borrowing remains restricted to infrastructure
  commands.
- Reflection scheduling state is now accessed through the authority-owned
  reflection repository. The application graph, scheduler, and relevance gate
  no longer expose, accept, or retain a raw scheduler-state collection; typed
  decoding, cooldown behavior, and corruption handling are unchanged.
- `OwnedCall` now captures the complete Python execution context for its
  one-shot thread. Interactive chat no longer stacks separate application and
  runtime-context callback wrappers, while authority, correlation, cancellation,
  outcome, and traceback behavior remain intact.
- Removed orphaned helpers from superseded file-storage, reasoning-tool,
  configuration, memory parsing, tool-result, and relation-rendering paths.
  Active configuration inspection, reasoning prompt generation, relation
  output, and repository compensation behavior are unchanged.
- Memory optimization and endpoint failover now call their shared classifiers
  directly, and the single legacy-email migration error no longer has an
  unused one-child exception hierarchy.
- Interactive session-header output now uses the existing CLI presentation
  module and the REPL's typed callback directly. The dedicated one-method
  presenter class and source module were removed without changing status
  refresh or rendered output.
- Daemon Reason composition now reuses its already-resolved model endpoints and
  queries only immutable readonly-tool membership from conversation runtime.
  The redundant two-field agent capability snapshot and its source module were
  removed without exposing the mutable tool registry.
- Removed the continuously rewritten JSON indexes for memory, profile, source,
  reason, and trace data, along with their `reindex` commands. Graph,
  relation, search, and trace views now read authoritative SQLite records
  directly; explicit user-requested exports remain unchanged.
- Daemon control success payloads no longer duplicate request type and status
  as fixed acknowledgement strings. Ping carries only the runtime
  `authority_id`, while shutdown and idempotent activity close return the
  shared exact empty payload. Health returns the unified scheduler snapshot
  directly instead of nesting it in a single-field response wrapper.
- The unified daemon scheduler now sleeps while executor capacity or resource
  lanes are blocked, fails chat closed when unavailable, and reports only
  payload-safe current degradation. A committed chat reply is no longer
  replaced by a failed curation/compression wake-up; durable scans recover both
  kinds of maintenance. The shared `@observed` policy now emits safe feature
  started/completed/failed events, and production daemon tasks enter through a
  closed typed construction boundary.
- Application composition is now the single authority path for initialized
  CLI, REPL, daemon, chat, reflection, persona, and evaluation work. Generic
  data commands use a validated administration API instead of raw
  collections; committed turns cross into memory as immutable DTOs;
  reflection receives foreign capabilities explicitly; worker threads carry
  the active application authority; and the daemon's one scheduler now has a
  closed task-name catalog. No service bus or parallel compatibility path was
  added.
- Conversation and memory now meet through explicit domain APIs instead of
  shared storage. A committed chat turn is projected through memory's generic,
  durable `observe()` inbox; the curator scans only pending observations and
  never opens conversation state. Conversation also exposes a bounded,
  read-only history API so reflection or reasoning can request chat evidence
  without receiving `ConversationStore`, locks, or persistence records. Schema
  v7 migrates unprocessed v6 curator ranges into durable observations.
- Persistent chat streams are now consistently named `conversation` across
  the CLI (`nuself conversation`, `:conversation`/`:c`), daemon protocol,
  storage, logs, traces, memory evidence, notifications, and internal APIs.
  `session` remains one transient client connection and `turn` remains one
  interaction; reasoning threads keep their separate reason-domain identity.
  Schema v6 provides an explicit reversible migration from v5 without changing
  message content or order. Completed replies are committed and presented
  before compression; daemon compression runs after memory curation on the same
  conversation resource, while bounded stage durations and context counts make
  slow context preparation observable without logging private content.
- The daemon now runs chat, memory curation, reflection, reasoning,
  notifications, and reason export through one bounded scheduler in one daemon
  process. Stable task identities coalesce duplicate wake-ups, resource keys
  serialize conflicting work without per-module locks, and one health snapshot
  replaces worker-specific lifecycle state. Dedicated worker supervisors,
  admission queues, timer schedulers, and export-worker threads were removed.
- Daemon chat now returns immediately after persisting the reply and publishes
  a durable memory observation for the unified scheduler instead of running a
  second model call in the request path. Requested observation IDs are
  coalesced, and periodic scans of the memory inbox recover missed in-memory
  wake-ups without opening conversation storage.
  Reusing a persisted chat `turn_id` with different input now fails before the
  model or tools run instead of creating a second conflicting turn. Chat state
  update and compression also preserve archived thread state instead of
  implicitly unarchiving it. The redundant branch-free outer `StateGraph` was
  removed; LangChain `create_agent` remains the single framework-native
  model/tool loop while NuSelf stages run as a direct typed pipeline. Stable
  turns now persist an internal pending marker before model/tool execution and
  clear it with the completed reply; interrupted or failed commits fail closed
  on retry instead of replaying a possibly committed mutation. Chat-turn trace
  projection now runs only after the completed thread state commits, outside
  the per-thread lock, so a failed save cannot leave provenance for a reply
  that was never persisted.
- Agent tools now use one orthogonal declarative policy path for identity,
  ownership, effects, confirmation, observation, and audit. The old
  effectful approval wrapper and ad-hoc StructuredTool factories are removed.
  Approval is supplied by a replaceable frontend port, while privacy-safe tool
  and approval activity uses the existing typed `chat/tool.activity` event for
  terminal, daemon, durable-log, and future web projections. Conversation
  composition now passes small, ownership-specific conversation and tool
  resource snapshots instead of forwarding a dozen repositories and services
  through nested constructors. Presentation activity now publishes directly
  through the existing runtime event publisher; the redundant frontend-event
  wrapper, sink, and adapter layer has been removed.
- Module dependency rules are now executable architecture gates. Agent tools
  return model-facing structured data without importing terminal renderers,
  establishing the first enforced adapter boundary for the v0.3.1 decoupling.
  A shared, lazy `ApplicationRuntime` now owns resolved paths, storage lifetime,
  and one application graph for both CLI and daemon process surfaces, including
  normal, interrupted, and exceptional teardown. Daemon chat and its tool
  runtime now receive graph-owned memory, profile, reflection, trace, and
  thread-storage collaborators instead of rebuilding them. Daemon curation,
  reflection, and reasoning workers reuse that graph's backend, repositories,
  outbox, recovery plans, and trace recorder. Reflection candidate generation,
  relevance evaluation, organization, and scheduling now receive explicit
  graph resources through application-owned composition. Direct and daemon
  chat also share one application-owned factory; reason, trace, persona,
  memory, reflection, and thread-storage tool collaborators are injected
  before the agent layer, and the conversation runtime no longer contains a
  root-based fallback composition path. Reflection schedule-state persistence is separated
  from orchestration into its own strict codec module, and model-backed
  relevance evaluation and candidate generation now have dedicated modules
  with injected gate and thread-context boundaries. Reflection promotion
  operations require explicitly composed repository, reason, and trace ports.
  Memory intake now receives
  its profile context explicitly instead of opening storage, and memory
  optimization receives the graph-owned entry, candidate, and profile
  repositories. Memory curation likewise requires the graph-owned backend,
  stores, repositories, recovery plans, and trace recorder; its structured
  actions, observation schema, settings, and result DTO now live in a dedicated
  contract module. Reason operations
  used by CLI, REPL, chat, reflection, and
  daemon workers now share application-owned composition; the core reason
  service requires explicit repository, workspace, and trace dependencies,
  while schedulers and export workers receive that existing service and
  schedulers receive the repository explicitly. The
  conversation graph runtime now requires its complete memory, thread,
  reflection, reason, trace, and persona capability set instead of rebuilding
  authority resources inside the agent layer. Persona definitions receive the
  graph-owned memory repository rather than opening storage from persona
  policy. Persona tools and reason advancement now also receive graph-owned
  prompt, trace, path, and workspace capabilities instead of selecting a
  second authority during tool construction. Chat thread persistence now
  receives resolved paths and storage explicitly, while CLI, REPL, daemon,
  curator, reflection, and chat composition share the application-owned
  factory. Logging terminal-warning schemas
  are isolated from the durable log engine in a dedicated runtime contract
  module. Trace
  repositories and services now require explicitly composed storage instead
  of resolving a hidden default backend or paths, and their concrete assembly
  is owned by the application layer rather than the trace domain. Profile
  persistence and aggregation now use the same explicit composition boundary,
  as do reason thread/step and reflection persistence; reason and reflection
  domains no longer import outward application composition. Memory entries,
  candidates, profiles, and sources now form one authority-scoped application
  graph with shared collaborator instances instead of resolving storage inside
  repositories. The notification outbox and its lock paths are now part of the
  same graph and likewise receive explicit authority resources. Persona prompts
  and memory curator recovery plans complete the persistence migration: both
  now receive graph-owned authority resources instead of resolving defaults
  inside their repositories. Memory-backed persona definition loading also
  receives the graph-owned memory repository instead of selecting storage.
  Persona agent tools and reason advancers now receive prompt, trace,
  workspace, path, and storage capabilities from application composition;
  reason scheduling no longer builds an advancer from a project root. Agent
  reason-export tools also receive their reason workspace explicitly instead
  of resolving runtime paths, and the output service no longer constructs a
  fallback workspace authority. Workspace storage itself now receives resolved
  runtime paths, and the daemon export worker borrows that store from process
  composition instead of creating it during startup.
  Reason-output section, chunk, manifest, progress, path, and planner schemas
  now live in a dedicated strict contract module, separate from export
  persistence and composition workflow.
  Notification delivery orchestration is now
  separated from outbox persistence and consumes an injected delivery plan.
  Memory persistence and query components now
  depend on a narrow profile capability contract instead of the concrete
  profile storage adapter. Reflection promotion likewise consumes only narrow
  reason-thread-start and provenance-recording ports, while executable gates
  keep domain and agent code independent of CLI/TUI presentation. Notification
  delivery orchestration now lives separately from outbox persistence and
  locking, without changing the package's public imports.
- Schema v4 replaces per-collection dynamic-column tables with one compact
  strict-JSON `records` table and makes namespaced workspace state part of the
  main authority. Its v3↔v4 migration is reversible. Reason exports now live
  under `exports/reason/` instead of creating structured workspace directories.
  Schema v5 removes the redundant prefix indexes through an explicit reversible
  migration, exact versioned schema identity is validated on open, and
  downgrade refuses to discard unexported workspace state.
- Database schema migration is now an explicit operator action rather than a
  side effect of opening storage. Versioned scripts under
  `scripts/database_migrations/` provide dry-run planning, exact targets,
  consistent pre-migration backups, cross-process serialization, and
  transactional paths. The runtime accepts only the current schema; every new
  post-v3 migration must also define its downgrade.
- Interactive startup no longer repeats historical record-decode Attention
  notices after a successful validated update of the same collection and
  record. Later, unidentified, and still-unrepaired failures remain visible.
- Transient model-availability failures now retry the same endpoint once before
  ordered failover. Readonly tool outcomes remain replayable while any
  write-capable outcome still suppresses replay. An empty chat memory search
  now requires one distinct broader query before reporting no stored match.
- Fixed a daemon-wide deadlock caused by holding the shared SQLite transaction
  across LangGraph model/tool execution. Chat turns now retain only their
  per-thread serialization lock during long work, then recheck and commit in a
  short transaction. Graceful stop/restart now has a 30-second ownership
  release budget while the authority lock continues to enforce one daemon
  process.
- Added `nuself data check` to report the current unique invalid memory or chat
  records and print validated edit/confirmed delete commands without exposing
  payloads or mutating data. One-time legacy-memory repair is now an explicit
  dry-run-first repository script rather than installed runtime behavior.
  Interactive Attention notices point to validation; undelivered completed
  chat replies point to `:history`, with daemon restart reserved for recurring
  transport failures.
- Ctrl-C during an in-flight interactive turn now cooperatively closes its
  daemon request socket and joins the owned send before returning to the
  prompt. Ctrl-D and all true session exits continue through transcript,
  curator, and storage cleanup exactly once. One-shot interrupts exit cleanly
  with status `130`, destructive confirmations cancel without mutation, and
  notification watch now honors both terminal EOF and `q`.
- Fixed interactive startup silently blocking behind a daemon chat turn.
  Thread snapshot reads now use SQLite's last committed view without competing
  for the long-lived per-thread mutation lock or a write transaction.
- CLI startup now performs side-effect-free readiness checks before opening
  domain storage, starting a daemon, or entering interactive chat. Commands
  that need an initialized authority exit with status `3` and an exact scoped
  `nuself init` command; interactive entrypoints also reject missing model
  configuration before they can appear to hang. Temporary daemon and transport
  failures use status `4`.
- Interactive chat now retains a failed retryable message with its original
  logical `turn_id` and exposes `:retry`, allowing a safe explicit retry even
  when the previous request may already have completed.
- Interactive chat now surfaces a grouped `Attention:` block for an unusable
  model configuration, an explicitly unselected workspace authority, unreadable
  persisted records, and daemon reply-delivery failures. Turn-time record
  failures are aggregated into actionable metadata-only notices instead of
  remaining hidden in developer logs or flooding the terminal one record at a
  time.
- Structured state is now SQLite-only in user and workspace authorities.
  Chat threads, curator cursors/plans, and scheduler state have joined the
  domain collections; file-backend fallback and `dev migrate` are removed.
  Missing canonical databases initialize atomically, while invalid existing
  authority still fails closed.
- Added `nuself data collections/list/show/export` for discoverable SQLite
  data and validated `data edit/delete` workflows for memory and chat threads.
  Editing preserves stable identity, shows a diff, confirms changes, detects
  concurrent updates, and writes metadata-only audit events. Internal
  operational collections remain hidden unless explicitly requested.
- The repository authority was migrated to schema v3 and verified before
  legacy JSON directories were retired. The public example now contains only
  configuration and source inputs; obsolete example profile/manifest/share
  state and frozen file-backend migration fixtures are removed.
- The committed public authority example now lives at `examples/.nuself/`,
  matching the v0.3.1 workspace layout and documentation. Repository-local
  `.nuself/` state and its migration lease are ignored.
- Legacy layout migration now uses the readable sibling lease name
  `.nuself.migration.lock` instead of leaving a double-dot filename.
- Current diagnostics and help now consistently say `authority root` and
  resolve exports relative to the selected authority. The obsolete
  `nuself.private` helper has been replaced by `nuself.authority`.

## v0.3.1 - 2026-07-30

- Introduces explicit user and workspace authorities:
  normal commands use `~/.nuself` (or `NUSELF_HOME`), while `--local` and
  `--workspace PATH` select isolated `.nuself` state. Workspace configuration
  inherits user defaults without merging databases or runtime state, and
  `init`, `dev paths`, and layered `dev config` expose the selected scope.
  Authority-specific daemons use short sockets keyed by a verified authority
  ID while persistent lifecycle metadata remains inside the authority.
- Added explicit, fail-closed `migrate-layout` publication from a v0.3.0
  checkout-local layout to a user or workspace authority. Migration preserves
  the source, serializes concurrent publishers, uses SQLite online backup for
  live databases, omits stale runtime/lock artifacts, validates staged state,
  and never merges with or overwrites an existing target.

## v0.3.0 - 2026-07-30

- The English and Chinese READMEs are now concise project front pages with a
  five-minute quick start. Detailed configuration, CLI, memory, testing, and
  contributor guidance lives in focused documents instead of duplicating
  implementation contracts and release history on the project homepage.
- The tag-triggered release metadata gate now runs inside the locked
  uv-synchronized environment, so src-layout package imports are available
  before release build and publication side effects begin.
- Existing v1 SQLite databases now acquire a stable cross-process schema lease
  before writable setup, then re-read the version under that lease so exactly
  one opener creates the genuine pre-v2 backup and performs the upgrade.
  Canonical ownership is inferred even for direct backend construction, while
  external v1 backups and public external backup destinations preserve parent
  and file permissions; managed thought-pack paths remain owner-only.
- Existing SQLite authority now uses lock-aware read-only validation with
  normal WAL coordination, never `immutable=1`. Ordinary startup checks only
  NuSelf schema identity rather than running a full-database `quick_check`;
  live concurrent writers, checkpoints, repeated opens, and crash-left WAL
  recovery are covered across processes. Redirected managed parents and
  invalid authority still fail before schema or business mutation, while
  explicit external SQLite paths retain their directory and file modes.
- `dev db-schema` now inspects only an already-active SQLite backend and cannot
  create an empty canonical database that hides file-backed data. SQLite
  opening requires an existing database; only atomic migration may create its
  unpublished temporary database.
- Configuration now rejects non-finite numeric values before timeouts reach
  daemon or provider clients, and schema acceptance tests use the JSON Schema
  dialect declared by the published document.
- File authority selection is now atomic with migration publication: a process
  paused before shared-lease acquisition cannot resume on obsolete files,
  closed file backends and their existing collections reject all access, and
  `dev migrate` publishes only to canonical `private/nuself.sqlite`.
- Managed private directories are now opened component-by-component without
  following symlinks, preventing redirected external directories from being
  chmodded, read, or populated with config, databases, locks, or runtime state.
- The v0.3 config loader now accepts the complete official v0.2.5 example,
  removes only retired `experimental.langmem_adapter` with a one-time warning,
  and raises a typed migration error for enabled legacy email setups missing
  `email.to_address` instead of exposing a generic validation failure.
- Runtime configuration validation is now type-strict, and a shared acceptance
  matrix proves behavior-level parity with the published JSON Schema,
  including email defaults, paired credentials, non-blank enabled fields, and
  header-control rejection.
- `inbox notify clear` now defaults to all terminal notifications and accepts
  `--status sent|failed|dismissed|all-terminal`; pending entries are never
  cleared, while failed selection includes uncertain adapter plans.
- Shared SQLite backends now isolate reads from uncommitted writes, immediately
  observe dynamic columns added by other processes, and reject mismatched
  record IDs instead of silently rewriting them.
- File-to-SQLite migration now refuses to run while any file-backed runtime is
  active and blocks new file authority during publication. The former custom
  `--db` destination has been removed because only canonical
  `private/nuself.sqlite` can become runtime authority.
- Notification delivery, dismissal, and deletion now serialize per entry
  across processes. Adapter attempts persist `delivering` before external
  effects and recover interrupted attempts as `uncertain` without automatic
  replay, preventing silent duplicate SMTP-style sends.
- Configuration is now strict and schema-parity tested, hides all credential
  inputs from diagnostics and representations, and hardens the private root
  and config file before reads. Email uses only the unified YAML configuration,
  including its recipient, while daemon, CLI, and REPL share one adapter plan.
- Developer health accepts an absent optional config file, and effective-config
  output now states that running daemons require restart after changes.
- Tests now use a domain-oriented hierarchy under `tests/unit/` with concise
  module names; opt-in real-provider checks live alongside them in
  `tests/live/` without entering default pytest or CI collection.
- The Anthropic adapter now avoids duplicate `/v1` paths and disables thinking
  so framework-forced structured tools remain valid.
- Real-provider verification now supports explicit `provider:model` selections
  and a maintained five-model OpenCode Go capability matrix.
- Added an explicit opt-in `tests/live/` suite for real LLM transport,
  LangChain structured-output, and NuSelf chat-boundary checks. Default pytest
  and CI never collect these network- and cost-bearing tests.
- Chat now preserves a valid final LangChain message from OpenAI-compatible
  agents that omit optional structured response state. Configured endpoint
  failures produce accurate fallback guidance instead of claiming that no API
  was configured.
- Effective config inspection now recursively flattens endpoint lists and
  redacts every API key instead of exposing aggregate endpoint secrets.
- `nuself dev migrate` now builds and validates a strict temporary SQLite
  database before atomically publishing it; corrupt or ID-mismatched source
  records abort without exposing a partial database, and in-place `--clear`
  migration has been removed. Orphan final-name SQLite sidecars block
  publication, while unpublished migration siblings never claim authority.
- Notification CLI, REPL, and daemon delivery now share one adapter-state
  pipeline; dismiss preserves delivery history, and crash recovery finalizes
  recorded adapter failures without implicitly retrying them.
- Memory candidate durability-uncertain commits no longer compensate their
  targets when candidate/target read-back fails or an accepted candidate has
  an unexpected target; typed ambiguity retains secondary observation errors.
- CI and release now require uv `0.11.21` and lockfile-managed Pyright
  `1.1.411`; release reruns Pyright and the full test suite and rejects
  lightweight tags or tagged commits outside `main` history before building.
- File-to-SQLite upgrades now normalize 0.2.x memory relation fields at the
  explicit migration boundary, and the release gate reads a frozen 0.2.5
  private-data fixture through the current repositories.
- CI and release automation now pins third-party actions to immutable commits;
  release artifacts also receive GitHub build-provenance attestations.
- The stable package is now `0.3.0`; release metadata gates enforce
  tag/package/runtime/changelog agreement, unified `uv build`, clean-wheel
  smoke tests, checksums, and Linux/macOS CI coverage.
- Thought-pack export names now reject Windows device names and trailing dots,
  matching the documented portable-filename contract.
- Job admission, delayed scheduling, and owned calls now share exact timeout
  validation that rejects booleans, NaN, infinity, and negative values.
- Email notifications now escape HTML content, canonicalize and restrict deep
  links to supported `nuself` actions, reject header control characters, and
  convert declared message-construction errors into stable delivery failures.
- Endpoint failover now recognizes structured 408 and transient 5xx provider
  statuses through direct, response, cause, and context fields without parsing
  exception messages.
- Short Chinese, Traditional Chinese, Japanese, and mixed-language durable
  memory signals now pass the curator fast gate instead of being excluded by
  an English-only marker list.
- Chat thread decoding now rejects malformed message members, boolean indexes,
  unknown message fields, and inconsistent absolute message indexes instead of
  silently dropping or repairing persisted data.
- Reason export jobs now request delayed online reconciliation when failure
  state persistence or a retry callback fails, avoiding daemon-restart-only
  recovery and immediate storage-failure loops.
- Notification outbox records now persist attempts and success independently
  for each stable adapter ID; interrupted delivery resumes without repeating
  adapters whose external effect was already recorded as sent.
- Notification outbox admission now serializes idempotency lookup and insertion
  across processes and storage connections, preventing duplicate intents from
  concurrent producers.
- Memory candidate acceptance now distinguishes an already-visible logical
  commit with uncertain crash durability from a failed commit, preserving the
  accepted candidate and target for explicit reconciliation instead of
  rolling one side back.
- File-backed collection deletion now synchronizes the parent directory and
  reports post-unlink durability uncertainty with a typed error.
- Explicit zero-valued importance and evaluation thresholds now round-trip
  without being replaced by defaults; numeric wire fields reject booleans.
- Thread rename, branch, archive, unarchive, and delete now coordinate with
  chat persistence through stable cross-process lock files.
- File-backed collections now reject path-like keys, record/key identity
  mismatches, symlinked records, and symlinked collection directories.
- Redacted caught callback, event-projection, protocol-decode, and rollback
  diagnostics before terminal or wrapper presentation.
- Curator runs and plan discard now use the same per-thread cross-process lock,
  preventing duplicate model work and repair races.
- Added payload-safe `memory plan show` and force-gated `memory plan discard`
  commands for diagnosing and repairing curator recovery state.
- Curator decisions are now durably resumable: cursor write failures reuse the
  saved action plan and deterministic candidates without another model call.
- Curator auto-accept storage failures now preserve the durable candidate,
  advance the source cursor, and avoid generating duplicates on the next run.
- Curator auto-accept now commits a reviewed MemoryEntry and accepted candidate
  together instead of promoting the entry in a separate post-commit write.
- Memory candidate acceptance now rolls back target create, merge, or delete
  when persisting the final accepted state fails.
- Daemon startup now refuses readiness when shutdown was requested while
  background workers were starting.
- Daemon startup now verifies that every registered background worker remains
  running before publishing readiness or accepting requests.
- Daemon workers that return before shutdown are now reported as unexpected
  exits in worker health and lifecycle logs instead of appearing as ordinary
  stopped workers.
- Persona discussion and `persona_think` now recover only from typed Agent
  failures; raw Agent implementation `RuntimeError` and `ValueError` failures
  propagate instead of appearing as normal persona fallback.
- Reflection relevance scoring and candidate generation now recover only from
  typed Agent failures or semantic domain-materialization errors; raw Agent
  implementation `RuntimeError` and `ValueError` failures propagate.

### Added

- Added `nuself daemon health`, backed by a typed daemon health request, to
  inspect background worker liveness, consecutive failures, last success, and
  last error.

### Changed

- Memory curator and optimizer now defer only typed `AgentError` invocation
  failures or semantic action-materialization errors; raw agent implementation
  `RuntimeError` and `ValueError` failures propagate instead of masquerading as
  valid deferred decisions.
- Invalid typed reason-export section plans now record a sealed
  `reason_output_section_plan_fallback` degradation before using the
  deterministic plan; diagnostic failure cannot replace that fallback.
- Memory-backed persona definition loading now records a sealed
  `persona_definition_load_failed` degradation when it falls back to builtin
  personas; diagnostic storage failure cannot replace the fallback.
- Daemon protocol failures now retain their source phase: request-envelope
  decode, direct typed payload rejection, and registered handler invocation
  have separate boundaries, so an internal `ProtocolError` is no longer
  mislabeled as malformed client input.
- Daemon request dispatch now distinguishes an unsupported request key from an
  `UnknownHandlerError` raised during registered handler invocation, preserving
  nested registry and middleware failure identity instead of mislabeling it.
- Closed daemon and REPL handler catalogs now prove exact registered-key
  coverage through the shared sealed `HandlerRegistry`, with typed missing and
  extra key failures instead of boundary-specific `RuntimeError` checks.
- Auxiliary structured logs now validate and persist one immutable audit
  envelope, eliminating duplicate identity/context capture and mutable-input
  time-of-check/time-of-use drift while preserving best-effort persistence
  failure reporting.
- Definition lookup now requires an explicitly sealed registry, and runtime
  owners such as `EventPublisher` reject partially composed registries before
  use so late registration cannot change their supported identity set.
- Local runtime jobs are now created through their sealed semantic registry;
  unknown names, disallowed producers, and invalid domain data fail before a
  `JobMessage` is returned, while queue ingress still revalidates decoded data.
- Process-local log callbacks now use an explicit bounded projection API.
  Invalid projections fail during scope composition, and attachment-scoped
  reentrancy guards prevent direct or mutual recursive log delivery.
- Interactive chat now owns its one-shot send thread through shared execution
  infrastructure. Polling, rendering, and control-flow failures wait for the
  in-flight send to finish instead of abandoning a daemon thread.
- Runtime events now expose explicit synchronous projection attachment instead
  of a general subscriber API. Projection callbacks must be bounded in-process
  work; independently progressing effects require an owned bounded queue.
- Reason export retry delays now use a shared owned scheduler that removes
  completed tasks promptly, rolls back failed starts, and cancels outstanding
  work atomically during shutdown.
- Reason export wake-ups now use bounded, identity-deduplicated admission that
  coalesces pending and in-flight jobs; capacity pressure triggers online
  manifest reconciliation instead of blocking callers or growing without bound.
- Filtered runtime-event subscriptions now require the complete registered
  producer/name identity, preventing same-named extension events from crossing
  subsystem subscriber boundaries.
- Daemon live-activity overflow is no longer silent: activity batches carry a
  dropped-event count, and the REPL recovers a detected stream gap from
  authoritative turn-scoped logs without replaying earlier activity.
- Chat compression now preserves thread persistence across every ordinary model
  exception by using the local summary, and records the degradation through a
  sealed `chat/compression_fallback` audit without conversation payloads.
- Agent invocation now distinguishes model unavailability, framework protocol
  violations, and invalid generated output. Endpoint failover uses provider
  exception types and structured HTTP status instead of error-message text.
- Thought-pack export names are now validated as portable file names, preventing
  absolute paths and traversal outside `private/exports/`.
- The directly imported `langchain` distribution is now an explicit runtime
  dependency instead of an accidental transitive dependency.
- CLI startup no longer replaces the process-global `warnings.warn` callable;
  the known LangGraph serializer deprecation is filtered only around the chat
  adapter import, while unrelated dependency warnings remain visible.
- Daemon raw process-log rotation failures now use a sealed warning contract
  with only the exception type and a fixed startup-continuation suffix.
- Agent tool-log callback and failure-reporter terminal diagnostics now use two
  sealed warning contracts with exact safe error fields instead of middleware
  string interpolation.
- Structured observability sink failures now use the fixed sealed
  `runtime/observability_sink_failed` terminal warning with exact typed fields
  instead of dynamically reusing each failed business audit identity.
- Logging-core terminal diagnostics now resolve through one sealed six-event
  warning taxonomy with exact ordered fields and one credential-safe renderer;
  corrupt-record diagnostics no longer render exceptions directly.
- Process-local log observer failures now use a sealed logging-core audit
  contract; diagnostics no longer persist callable class names or duplicated
  exception type metadata.
- REPL Reason thread completion failures now resolve through the sealed Reason
  audit registry instead of caller-selected generic observability; the event
  no longer stores redundant `completion=reason_threads` metadata.
- Shared Chat, Memory, Persona, Reason, and Reflection endpoint failover
  observations now use one sealed audit contract with fixed presentation and
  exact safe metadata; endpoint base URLs are no longer persisted.
- Agent tool completion logs now come exclusively from framework middleware
  through one validated outcome projection shared by Chat, Reason, and
  persisted Reason step snapshots. Approval wrappers no longer emit duplicate
  pre-call or executed records, and failed snapshots retain the canonical
  top-level error.
- Approval prompts and decisions now use one sealed audit contract with fixed
  projection policy and exact metadata. Explicit rejection and EOF safe
  rejection are durably distinguished, while approval events no longer imply
  that the approved tool completed successfully.
- Secondary log persistence and internal event subscriber failures now use two
  sealed infrastructure diagnostics with exact metadata:
  `observability_projection_failed` and
  `internal_event_delivery_failed`. Domain-specific write/delivery failure
  aliases and free-form failure projections were removed.
- Daemon request rejection, chat completion/failure, and shutdown acceptance
  now resolve through one sealed request-audit registry. Request handlers no
  longer choose audit presentation or schema, and accepted shutdown records
  carry an explicit `accepted` status.
- Daemon socket read, unexpected dispatch, response encoding, and response
  delivery failures now use one sealed transport-audit registry. Undecoded
  requests no longer persist the internal `unknown` sentinel as a request
  identity.
- Daemon worker join timeouts and lifecycle cleanup failures now use one
  sealed operations-audit registry. Cleanup diagnostics retain every ordered
  step/error chain, while timeout metadata no longer repeats its
  `timed_out` status.
- Default storage backend close and outer CLI cleanup failures now use one
  sealed storage operations-audit registry. Daemon and CLI cleanup diagnostics
  share one canonical ordered `{step,error}` projection instead of retaining
  only cleanup step names.
- Internal job wake-ups now resolve through sealed name, producer, and payload
  definitions before queue mutation; Reason export workers reject invalid jobs
  at ingress instead of queueing and later emitting
  `export_job_type_ignored`.
- Reason lifecycle, proposal, scheduler, advancer, trace, output, and daemon
  export-worker audits now use one sealed Reason-owned registry with fixed
  messages and exact metadata; audit records no longer duplicate private
  topics, summaries, mandates, terminal reasons, artifact paths, runtime
  correlation, or secondary exception details.
- Memory curation, post-chat scheduling, and trace-persistence failures now use
  one closed Memory-owned audit registry; clients no longer emit the redundant
  `curator_changed` record or persist free-form curator summaries and duplicate
  correlation identifiers in audit metadata.
- Chat supervisor, LLM failover, daemon/one-shot client, and REPL diagnostics
  now use one closed Chat-owned audit registry; retry records no longer persist
  endpoint URLs, previous exception text, subscription IDs, duplicated request
  IDs, or redundant exception-type metadata.
- Notification delivery audits now use one closed Notification-owned schema;
  log-only, dry-run, unavailable, configuration, and delivery-failure records
  no longer duplicate notification content, deep links, idempotency keys,
  recipients, or SMTP configuration.
- Persona consultation, discussion, fallback, lifecycle-trace, and interactive
  command audits now use one closed Persona-owned schema; audit records retain
  only stable ids, stages, decisions, and counts instead of duplicating user
  topics, candidate text, synthesis, discussion utterances, or model reasons.
- Daemon lifecycle audits now use a closed immutable event registry with fixed
  projection defaults and exact per-event metadata schemas; producer mistakes
  fail before reaching the best-effort log sink.
- Daemon start/stop now return explicit transition outcomes, and one-shot plus
  interactive restart share one audited orchestration that reports both stop
  and start outcomes instead of inferring work from the final status.
- Daemon status observation is now shared across CLI and REPL surfaces; the
  default launcher reuses its initial project-validated snapshot instead of
  immediately repeating the same ping and ownership probe.
- Daemon status now exposes explicit `stopped`, `owned_unready`, `ready`,
  `inconsistent`, and typed `unknown` phases; ambiguous ownership never falls
  back to one-shot execution or masquerades as stopped.
- Daemon `started`/`stopped` lifecycle records now represent actual readiness:
  `started` is published only after every background worker starts and before
  the first request can be accepted.
- Daemon startup now reconciles stale socket and PID metadata explicitly while
  holding the instance lock, audits successful crash recovery, and publishes
  the current PID only after Unix-socket binding succeeds.
- Daemon shutdown now uses bounded graceful request and instance-lock release
  as its ownership boundary; stale PID metadata is never used for signal
  escalation, and stop/restart failures are typed and consistently audited.
- Daemon startup now distinguishes spawn failure, early child exit, and
  readiness timeout through one typed lifecycle error; every CLI surface uses
  the same safe message and failed-start audit projection.
- Daemon raw stdout/stderr now rotates before startup at 5 MiB with three
  owner-only backups; retention failure warns safely without blocking startup.
- Structured logs now avoid redundant directory synchronization for repeated
  appends to the same active inode through a bounded process-local cache,
  without batching or weakening per-record data-file durability.
- Memory optimizer activity now uses structured audit events, while daemon
  stdout/stderr is isolated in `daemon-process.log`; component JSONL files no
  longer have raw-text writers.
- Structured-log appends now sync each complete record before acknowledgment,
  durably sync rollback truncation, and report persisted/not-persisted/uncertain
  lifecycle outcomes explicitly.
- Shared atomic text/JSON writes now sync temporary-file content before
  replacement and the parent directory afterward, with an explicit
  post-replacement durability error when crash persistence is uncertain.
- Private text/JSON state and internal chat transcripts now use owner-only
  directories and files (`0700`/`0600`) at the shared atomic write boundary.
- SQLite databases and sidecars, internal thought-pack snapshots, append-only
  logs, lock files, and internal append streams now share the same owner-only
  private filesystem boundary.
- Every persisted audit projection now sanitizes credential-like message,
  error, and nested metadata fields at the canonical log sink, including
  runtime-event projections, without mutating the source envelope or weakening
  strict JSON validation.
- Agent tools, persona, reflection, reason, notification, daemon payload, and
  configuration adapters now share safe caught-exception rendering; retry and
  compatibility classification remain based on the original exception.
- CLI chat, REPL, transcript, and command adapters now share safe exception
  presentation, preventing caught exceptions with credentials or broken string
  renderers from leaking or replacing the intended command result.
- Daemon exception responses now use one protocol-owned safe constructor, and
  compact exception chains sanitize credentials by construction instead of
  relying on each socket or request handler to remember redaction.
- Log-observer and agent-tool failure projections now share safe credential
  redaction for structured records, captured outcomes, and terminal warnings;
  original observer and tool exceptions remain unchanged.
- LLM provider failure diagnostics now redact labeled credentials,
  authorization and bearer values, credential-bearing query parameters, and
  common raw provider keys before truncation and persistence.
- Runtime event and daemon error reporting now share fail-safe compact
  exception-chain formatting. Duplicate cause messages are omitted, and an
  exception with a broken string renderer can no longer replace the original
  failure.
- Runtime event payload validators now run exactly once against the immutable
  envelope payload that subscribers receive, eliminating raw/frozen
  double-validation drift.
- Shared agent fallback classification now also surfaces import, lookup, memory
  exhaustion, name resolution, unimplemented-path, recursion, syntax, and
  interpreter-system errors instead of treating them as model degradation.
- Chat persona discussion now surfaces assertion, attribute, and type errors
  instead of appending them to the answer as an ordinary discussion failure.
- Persona activation, contribution, and synthesis no longer turn assertion,
  attribute, or type errors into neutral fallback output; chat and persona now
  share one agent failure classification.
- Approval prompts now treat only stdin EOF as a safe-default decline;
  rendering, terminal-output, and unexpected input failures surface normally
  instead of being mislabeled as a user rejection.
- Chat no longer retries or silently replaces assertion, attribute, or type
  errors with a local fallback response. After tool execution it still
  suppresses every retry, then propagates the implementation failure unchanged.
- Memory mutation tools now report only genuinely absent entries as
  “not found”; repository, decoding, persistence, and programming failures
  remain real tool failures instead of being mislabeled as user input errors.
- Auxiliary structured-log projections now use one typed observability
  boundary, and their failure diagnostics consistently identify the original
  `audit_event`.
- Agent tool logging and capture now consume the same immutable typed outcome
  instead of parallel callback arguments. Non-JSON tool arguments still reach
  the framework tool; projection failure cannot replace its result or error.
- Reason proposal, background advance, and output planning/composition/PDF
  audits now use the shared auxiliary projection boundary. Audit-store failure
  no longer blocks an approved thread, a persisted step/cooldown, or durable
  export artifacts and progress.
- Reflection scheduling logs now use the shared auxiliary projection boundary.
  Schedule blocks, filtering, discussion, fallback, and completed-cycle
  records can no longer change reflection decisions when the log store fails.
- Daemon-backed and one-shot chat results, curator status, and REPL transport
  retries no longer fail or change classification when their auxiliary audit
  record cannot be written. Uncertain audit persistence is reported separately
  without retrying the original record.
- Structured log append failures now distinguish a cleanly rolled-back write
  from an uncertain close-time outcome. The reported lifecycle error preserves
  write, rollback, and close causes and explicitly warns when the record may
  already have persisted.
- CLI one-shot and interactive invocations now release their shared SQLite
  storage backend on every exit path. Cleanup failures retain the original
  command error instead of silently leaking the connection or masking failure
  provenance. Developer migration and schema inspection also close their
  temporary SQLite connections, while storage inspection reuses the shared
  backend.
- Thought-pack export now uses SQLite's online backup API, so committed WAL
  data is included and exports remain consistent during concurrent writes.
- Thought-pack import now rejects corrupt, foreign, partial, and unsupported
  future SQLite schemas before creating an imported file, while preserving
  supported legacy sources unchanged.
- Thought-pack inspection now shares the same read-only validation rules and
  no longer initializes or migrates the database being inspected.
- CLI, REPL, and background scheduling now use one reason-layer factory to
  compose `ReasonAdvancer` workspace and model dependencies. A directly
  constructed scheduler with a project root now loads configured endpoints
  instead of silently creating an empty advancer; explicit injected endpoints
  and tools remain authoritative.
- Reason prompt generation no longer constructs configured models once for an
  availability preflight and again for the real structured agent. The shared
  agent invocation is now the sole availability boundary; no-model failures
  remain `ReasonPromptError` with the shared runtime error as their cause.
- Chat response now uses the shared agent endpoint runner for bounded
  same-endpoint retry, availability failover, success preference, and
  diagnostics. Protocol and structured-output failures retry the current
  endpoint once but no longer probe another endpoint; any tool outcome still
  suppresses all replay before the runner can invoke again.
- Chat runtime and response synthesis no longer accept `llm=` or construct
  `default_llm()`. Missing endpoints, exhausted endpoints, and tool-safe retry
  suppression now enter an explicit deterministic local response policy that
  produces typed chat output; generated test behavior uses
  `ConversationResponseService`. The now-unused raw `ChatLLM`,
  `LocalFallbackLLM`, and private text failover adapters have been removed from
  `nuself.llm`.
- Chat response services and evaluation fixtures now exchange
  framework-native LangChain messages directly. The temporary NuSelf
  `ChatMessage` DTO and its redundant conversion layer were removed.
- Removed the unused LangMem adapter, its dead `experimental.langmem_adapter`
  flag, and the direct `langmem` dependency. Memory generation now has no
  orphaned first-endpoint-only model runtime beside NuSelf's shared agents.
- `ReasonAdvancer` now builds equivalent agents for all configured endpoints
  and uses shared availability failover before any tool runs. Once middleware
  records a tool outcome, endpoint switching is suppressed with a chained
  `ReasonAdvanceError`, preventing workspace or persona tool replay.
- Shared agent middleware now transfers tool execution through immutable typed
  `ToolOutcome` records with distinct result/error fields. Reason tool outcomes
  are projected even when the enclosing agent later fails, so executed or
  failed tools no longer disappear or become mislabeled successful results.
- Chat model retry and endpoint failover are now suppressed after the current
  agent invocation records any tool outcome. Provider or structured-output
  failure can no longer replay a mutation through a fresh agent run; failures
  before the first tool retain existing bounded retry and failover.
- Conversation compression now uses an optional shared `TextAgent` with
  LangChain messages instead of `ChatLLM.complete()`. Missing, failed, or empty
  model-backed compression retains the bounded deterministic local summary as
  an explicit persistence-safety fallback.
- Reason export body composition now uses an injected shared `TextAgent` with
  LangChain messages and non-empty output validation. Direct
  `default_llm().complete()` and its hidden local configuration-warning output
  were removed; unavailable or empty generation enters the durable export
  retry/failure state machine.
- Reason export chapter planning now accepts only an exact
  `ReasonSectionPlanOutput` through the shared structured-agent runner.
  Prompted JSON, text parsing, field coercion/defaulting, and partial sibling
  acceptance were removed; malformed or incomplete ranges use the
  deterministic planner as one complete fallback.
- Global and thread-scoped `persona_think` now use an injected framework-native
  `TextAgent` with LangChain messages and a required non-empty natural-language
  result. Both direct `default_llm().complete()` paths and the hidden local
  fallback were removed; text and structured agents now share one endpoint
  failover primitive.
- Reason thread prompt generation now uses exact `ReasonPromptOutput` through
  the shared structured-agent runner. Direct `default_llm().complete()`, raw
  response trimming, and the parallel text-model protocol were removed;
  unavailable or malformed generation still fails thread creation without
  persisting a partial thread.
- Persona graph activation, contribution, and synthesis now share
  `PersonaGraphAgents` and the common exact-schema LangChain runner. The graph's
  private endpoint loop, direct structured-output binding, prompted JSON/text
  parsing, and legacy LLM-backed class protocol were removed; deterministic
  no-agent and failure fallbacks remain.
- Persona discussion scoring, participant selection, and moderator judgment now
  use three exact-schema agents through the shared LangChain boundary.
  Prompted/fenced JSON, generated defaults, extra fields, score clamping, and
  the discussion `llm=` protocol were removed while stage fallbacks remain.
- Reflection candidate generation and relevance scoring now use the shared
  LangChain structured-agent boundary. Generated defaults, prompted/fenced
  JSON parsing, extra fields, score clamping, and legacy `llm=` injection were
  removed; malformed typed output keeps the existing fail-closed behavior.
- Memory curator and optimizer now use the shared LangChain structured-agent
  boundary and accept only typed action batches. Their prompted-JSON,
  fenced-text extraction, parser helpers, and legacy `llm=` injection paths
  were removed.
- Manual memory intake now runs through a shared LangChain structured-agent
  boundary and accepts only its typed `structured_response`. Prompted JSON,
  fenced-text extraction, dictionary state, and the legacy text-LLM injection
  path were removed.
- Manual memory intake now requires a complete strict generated schema for
  type, title, tags, confidence, and importance. Unknown fields, coercive
  values, invalid tag counts, and out-of-range scores now fail the command
  instead of being defaulted or clamped.
- Memory optimizer responses now use strict, extra-forbid action schemas with
  bounded confidence. Every generated action is validated before candidate
  dispatch; one invalid action defers the complete decision instead of
  producing candidates for valid siblings.
- Memory curator responses now use strict, extra-forbid action schemas with
  bounded confidence. Every generated action is validated before dispatch; one
  invalid action defers the complete decision instead of partially applying
  valid siblings.
- Persona activation, contribution, and synthesis now require strict typed
  LangChain outputs. Dictionary compatibility, unknown fields, coercive types,
  and out-of-range confidence values now fail the endpoint instead of being
  accepted into persona state.
- Reason advances now consume LangChain's typed `ReasonStepOutput` directly.
  The manual dictionary parser and its filtering, clamping, and defaulting
  fallbacks were removed; malformed generated steps now fail validation
  instead of being silently rewritten.
- Chat responses now use framework-native `structured_response` as the sole
  model protocol. Prompted/fenced JSON and LangChain message-state fallbacks
  were removed; no-model local chat remains a plain-text deterministic path.
- Removed the `ChatAgent` class-name alias. Production composition, tests, and
  public imports now use `ConversationGraphRuntime` directly.
- Reason not-found, prompt, advance, and transition failures now use a declared
  domain exception hierarchy. CLI and REPL reason commands keep concise output
  for those expected outcomes without relabeling unrelated `RuntimeError`
  implementation failures as user errors.
- Recoverable local REPL `:persona` and `:history` failures now write
  privacy-bounded structured diagnostics while preserving their concise
  command result. Diagnostic storage failure cannot terminate the session or
  replace the original error.
- Daemon and REPL lifecycle owners now share one ordered named-cleanup runner.
  It retains `BaseException` failures while leaving domain-specific lifecycle
  errors, diagnostics, ordering, and primary-error policy with each owner.
- REPL exit now runs transcript auto-save and memory curation exactly once each
  and attempts both. Named cleanup failures are aggregated without losing an
  existing main-loop exception or allowing diagnostics to replace it.
- The live-chat send-thread boundary now observes unexpected callback
  exceptions without crashing the REPL, while preserving `KeyboardInterrupt`,
  `SystemExit`, and other control exceptions across the thread boundary after
  subscription cleanup.
- REPL daemon-activity open, poll, drain, and close failures are now observable
  with structured stage and client context. Live-log transport degradation
  cannot alter chat results, and persisted turn events are recovered through
  the incremental cursor when possible.
- Daemon client connection errors now retain their transport phase, request
  identity, retryability, and possible-completion state. REPL chat no longer
  retries local request-encoding or typed response-payload schema failures.
- Daemon response encoding failures are now distinct from socket delivery
  failures. Invalid or oversized handler responses fall back to a bounded
  request-correlated error frame when the connection remains writable.
- Daemon server, CLI, and interactive lifecycle audits now share one observable
  projection boundary. Audit storage failure cannot alter lifecycle execution,
  status output, or exit decisions.
- Daemon chat failure/completion and shutdown-request audits now use shared
  observable boundaries. Audit storage failure cannot replace the original
  chat error, invalidate a completed response, or block the shutdown flag.
- Email and macOS real-delivery failure diagnostics now use shared observable
  reporting. Diagnostic storage failure no longer replaces the adapter's
  `False` result or prevents the outbox from persisting a failed attempt.
- Memory curator activity now uses structured best-effort audit events instead
  of raw `memory.log` appends, and curator trace/organizer completion
  projections cannot replace committed candidate, cursor, entry, or reflection
  results. Update traces retain the actual curator action.
- ReasonService lifecycle audits and post-persistence traces now use shared
  observable boundaries. Projection failure cannot replace committed thread,
  step, transition, or deletion results, and delete success is logged only
  after authoritative deletion.
- Daemon reason-export lifecycle and failure audit writes now use the shared
  observable boundary. Audit storage failure cannot suppress durable retries,
  block composition on degraded progress, truncate reconciliation, or undo
  shutdown drain state.
- LLM endpoint preference and chat retry/failover/fallback/finalize diagnostics
  are now isolated from model control flow. Audit or derived-state persistence
  failures no longer discard valid responses or prevent configured fallback.
- Reflection trace/organizer failure and corrupt schedule-state diagnostics now
  use shared observable reporting. Diagnostic storage failure cannot interrupt
  an already-persisted cycle or change fail-closed scheduler/cooldown behavior.
- Reason advancer, scheduler, and output-runner failure logs now use shared
  observable reporting. Audit storage failure cannot mask the original
  advancer/runner exception or turn a cooled-down scheduler failure into a new
  raised error.
- SQLite transaction cleanup errors now expose structured `primary_error` and
  `rollback_error` fields for body, interruption, commit, and rollback-only
  failures, while retaining the original operation as the explicit cause and
  resetting transaction-local state.
- Daemon instance-lock acquire and release now retain both flock/unlock failure
  and simultaneous file-handle close failure in a typed
  `DaemonInstanceLockCleanupError`, instead of allowing cleanup to mask lock
  ownership state.
- Atomic text/JSON persistence now retains both the original write/replace
  failure and a simultaneous temporary-file cleanup failure in a typed
  `AtomicWriteCleanupError`, instead of allowing unlink failure to mask the
  authoritative storage error.
- Standard persona graph LLM degradation is now observable across structured
  endpoint failover, contribution generation, synthesis, and activation.
  Diagnostic storage failure cannot stop failover or replace the existing
  deterministic fallback result.
- Competitive persona discussion now records scoring, participant-selection,
  and moderator-judgment degradation under the caller's project runtime.
  Diagnostic failure cannot replace its existing neutral or deterministic
  fallbacks.
- Process-local log observer failures now fall back to a contextual
  `RuntimeWarning` when their structured `log_observer_failed` diagnostic
  cannot be persisted, instead of becoming completely invisible. Observer
  failures remain isolated from audit writes, later observers, and business
  operations, even when process warning policy promotes warnings to errors.
- Approval-gated tools now treat prompt, execution, and approval audit writes
  as observable best-effort effects. Audit storage failure no longer suppresses
  the prompt, changes a decline, or replaces an approved tool result; degraded
  diagnostics fall back to a runtime warning if structured logging also fails.
- Daemon-backed, one-shot, and interactive retry client chat operations now
  establish one `source="client"` runtime scope. Transport, completion,
  retry, and post-turn curation audits inherit thread/turn correlation instead
  of reconstructing it per write, while caller request/job/trace context is
  preserved and restored.
- Chat lifecycle now publishes registered `turn.started`, `turn.completed`,
  `turn.failed`, and `turn.reused` runtime events. The completed event is
  emitted only after the thread update is durably saved; event subscriber
  failures cannot replace a completed response or mask the original chat
  failure.
- Daemon worker lifecycle activity now flows through the registered runtime
  event publisher as `worker.started`, `worker.failed`, and `worker.stopped`,
  with structured audit logs attached as a subscriber. Subscriber failure no
  longer changes worker execution or health transitions, and worker-specific
  failure names are retained as `operation_event` metadata.
- Removed the unused process-global `ApprovalManager` callback registry.
  Approval-gated tools continue to use the synchronous decorator boundary;
  deferred approval must use a future durable typed contract instead of
  retaining arbitrary Python callables.
- Structured audit writes now reject unknown components and malformed event
  names before filesystem access. Shared backend lifecycle diagnostics use the
  new `storage` log component, available through `nuself dev logs --component
  storage`.
- Structured component logs now rotate at 10 MiB with three retained backups,
  using cross-process-safe sidecar locking; diagnostics read retained backups
  and live cursors follow file replacement without dropping unseen events.
- Daemon-attached interactive chat now receives turn-scoped live activity over
  a bounded subscription transport instead of polling shared log files; local
  one-shot sessions retain the incremental file cursor.
- Redesigned the interactive tool-approval prompt to match the REPL theme. It now
  shows a single colored `[component] approval required  tool=<name>` banner with
  the pending action indented below and an `approve? [y/N]` question, replacing the
  duplicated `[approval_prompted] ...` / `Confirm execute ... ? (y/n):` lines. The
  structured `approval_prompted` log event and the tool's JSON return contract are
  unchanged.
- Persona structured-output generation now fails over across all configured LLM
  endpoints on any error (not only availability errors) and logs each failure as
  `persona/persona_structured_failed`, instead of silently returning no contribution.
- A malformed or unreadable `private/config.yaml` now prints a one-line warning and
  falls back to defaults; previously any load error was swallowed silently, which also
  hid unrelated programming errors.
- Performance: `ConfigSystem.load()` memoizes results per file `(path, mtime, size)`
  so repeated loads in one process no longer re-parse the YAML; chat tools share one
  reason/trace/memory service instance per turn instead of opening a new storage
  backend per call; the persona moderator turn no longer makes an unused synthesizer
  LLM call; and the notification outbox and reason `get_job` no longer rescan whole
  collections for a single lookup.
- Performance: memory retrieval expansion now projects the symbolic graph once per
  `search()` instead of rebuilding it from `list()` for every transitive relation of
  every match; the SQLite backend caches each table's columns (was a `PRAGMA` per
  read/write) and `SqliteCollection.find()` filters with a SQL `WHERE` clause instead
  of loading and deserializing the whole table.
- Runtime dependencies imported directly by NuSelf are now declared directly,
  and built package metadata uses the public README instead of `AGENTS.md`.
- Reindex commands now write real rebuildable JSON projections under
  `private/derived/`; shared memory, persona-tool, and CLI handle helpers replace
  duplicated implementations.
- `nuself dev eval` now reports one structured result per fixture scenario and
  derives totals and exit status from those results. Notification evaluation no
  longer launches a nested pytest process or assumes a fixed fixture count.

### Fixed

- REPL session headers now follow one consistent lifecycle: once at startup,
  after every completed chat turn, and after commands that request a redraw.
  Previously the first turn reprinted the header but later turns with unchanged
  status/thread silently suppressed it.
- Isolated LangGraph tool-log projection failures so an unavailable audit sink
  no longer replaces a successful tool result or masks the original tool
  exception; the failure is reported as a structured degraded event when
  possible.
- Interactive chat send callbacks now preserve the exact thread/turn runtime
  context across their worker-thread boundary without inheriting stale
  request, job, or trace identity. Transcript capture keeps low-level activity
  from the current chat path while excluding correlated background subsystem
  audit records.
- Reason advances now use the shared runtime context as the single active
  thread identity for workspace and thread-local persona tools. Manual and
  scheduled failure logs preserve their caller correlation and reason thread
  without a parallel reason-specific context.
- Request-scoped live log observers now compose when middleware scopes are
  nested. A failed activity projection no longer suppresses later observers or
  turns an already-persisted audit event into a failed business operation;
  failures emit a non-recursive best-effort diagnostic.
- Log metadata is now captured as one detached, recursively immutable JSON
  snapshot before audit persistence and live projection. Caller or observer
  mutation cannot change queued activity, and invalid keys, values, or
  non-finite numbers fail before a partial record is written.
- Per-turn agent tool deduplication now uses canonical strict JSON arguments
  instead of `default=str` coercion. Invalid non-JSON arguments bypass the
  cache without blocking execution, and daemon activity no longer
  re-normalizes validated log records.
- File, SQLite collection, and reason-workspace persistence now share strict
  JSON encoding. Invalid or non-finite values fail before file/schema/row
  mutation; existing records remain intact, and an invalid workspace batch
  rolls back earlier operations.
- Daemon JSONL transport now uses a shared 1 MiB request/response frame limit,
  requires newline-complete UTF-8 JSON, times out stalled server reads, and
  rejects incomplete, extra, non-finite, or response-id-mismatched frames.
  Client disconnects during response delivery are observed without escaping
  the server connection handler.
- Daemon request/response envelopes now reject duplicate or unknown fields,
  boolean protocol versions, empty request ids, recursively non-finite JSON
  values, and response status/error mismatches on both encode and decode.
- Daemon request payload codecs now reject misspelled fields and invalid
  optional values instead of silently ignoring or defaulting them. Control
  requests require empty payloads, while `echo` remains intentionally open.
- Daemon chat, health, activity, ping, and shutdown clients now decode typed
  success payloads. Explicit daemon rejections remain application errors,
  while malformed successful responses fail as connection/protocol errors
  instead of being skipped, defaulted, or coerced.
- Reason export workers now activate each queued job's saved runtime context.
  Export and retry logs preserve top-level request, turn, trace, job, thread,
  and worker-source correlation instead of relying only on repeated metadata.
- Notification outbox entries now persist their originating runtime context,
  preserve it through state transitions, and restore it per delivery. Adapter
  logs retain origin correlation under the notification worker source; legacy
  entries without context remain readable with an empty context.
- Every scheduled memory, reflection, reason, and notification-delivery tick
  now runs in a fresh isolated job context. Nested domain work and failure logs
  share that tick id, while reused worker threads cannot leak prior
  request/thread/turn/trace identity into later iterations.
- Daemon execution now borrows SIGINT/SIGTERM handlers explicitly and restores
  the exact previous process handlers on every exit path. Partial installation
  rolls back already-changed signals, and restoration failures remain
  retryable and participate in lifecycle cleanup aggregation.
- Daemon shutdown now attempts every worker, project-scoped backend, socket,
  PID, and instance-lock cleanup step even when earlier steps fail. Named
  cleanup failures are retained together with any bind/serve error, worker join
  timeouts prevent a false `daemon/stopped` event, and one daemon no longer
  resets other projects' cached backends.
- Daemon background workers now share one supervised iteration boundary.
  Unexpected target exits and per-iteration failures update health with
  correlated `daemon.worker.<name>` diagnostics, and a logging failure can no
  longer terminate an otherwise recoverable scheduled loop. Export worker
  dependencies are initialized synchronously before its thread starts.
- SQLite shutdown now reports WAL checkpoint and connection-close failures
  instead of silently claiming success. Failed closes remain retryable,
  initialization cleanup preserves the original failure, and resetting
  process-default storage attempts every owned backend before reporting errors.
- SQLite dynamic columns now decode strictly as JSON. Corrupt rows are reported
  and isolated during collection reads instead of leaking raw column text into
  domain models, and JSON null now round-trips as a present `None` value.
- Local and LangChain compatibility response extraction now share one strict
  codec. Malformed protocol-looking JSON, unknown fields, invalid epistemic
  status or confidence, and visible tool-call text can no longer silently
  become the user-visible answer.
- Styled interactive prompt capability and IO failures now emit
  `chat/interactive_prompt_failed` before falling back to built-in input.
  Unexpected prompt failures and user interrupts are no longer covered by a
  silent local exception handler.
- Reason export progress reads now distinguish a normally missing file from
  permission and other filesystem failures. Progress snapshots are decoded
  strictly instead of filtering or coercing invalid chunk indexes.
- Reason-thread scheduling timestamps now require timezone-aware ISO-8601
  values. Corrupt cooldown records are reported and isolated before scheduling
  instead of silently becoming eligible for background advancement.
- Reason export job listing now reports and isolates malformed manifests
  without exposing their contents. Direct lookup no longer turns corrupt
  manifests or authoritative filesystem failures into an ordinary not-found
  result.
- Notification outbox timestamps are now decoded as timezone-aware ISO-8601
  values. Malformed records are reported and isolated during listing, invalid
  retention arguments are rejected, and dismissed-entry deletion failures are
  no longer silently swallowed.
- Present-but-invalid `private/email.toml` files now emit a payload-safe
  `outbox/email_config_invalid` diagnostic. Syntax, section, required-field,
  port, TLS, and credential-pair errors no longer silently look like an absent
  configuration file.
- CLI persona create/enable/disable trace failures now emit
  `persona/trace_recording_failed` after the successful mutation instead of
  being silently discarded.
- Recoverable post-chat memory-curator failures now emit an inherited-context
  `memory/post_chat_curation_failed` event while preserving the completed chat
  reply. They no longer silently appear as an ordinary "no memory change".
- Reason export state and artifacts, chat threads, and persona prompt records
  now use one shared unique-temp atomic writer. Fixed-name temporary-file
  collisions and subsystem-specific failure cleanup can no longer expose
  partial runtime state.
- Daemon PID metadata is now atomically published and strictly decoded.
  Malformed, empty, zero, or negative PID files emit a payload-safe diagnostic
  instead of silently looking identical to a missing PID file.
- Daemon startup now holds a per-project cross-process instance lock before
  touching socket or PID resources. Concurrent starts no longer risk deleting
  a live daemon's socket; the contender exits visibly without modifying the
  current owner's files.
- The derived LLM endpoint preference is now versioned, strictly validated, and
  atomically written. Corrupt, invalid, or stale state emits a payload-safe
  diagnostic and safely returns to configured endpoint order instead of
  failing silently.
- Reflection schedule state is now versioned, strictly validated, and written
  atomically. Corrupt or partial state fails closed with a payload-safe
  diagnostic instead of silently disabling cooldown, interval, or daily-cap
  protection.
- Persona activation and competitive discussion now use strict typed schemas as
  their sole prompted-JSON parse boundaries. String booleans, numeric strings,
  and partially malformed persona selections take the existing safe fallback
  instead of being coerced or partially accepted.
- Reflection relevance and candidate generation now use their typed schemas as
  the sole parse boundary; malformed batches, string booleans, and unknown
  candidate types take the safe fallback instead of being coerced or partially
  accepted by a second handwritten parser.
- Thread-scoped persona name indexes are now validated against authoritative
  prompt files and atomically rebuilt when missing, malformed, or stale;
  renaming a prompt no longer leaves its old name as an alias.
- Recoverable memory-curator auto-accept failures now retain the durable pending
  candidate and emit `memory/auto_accept_failed`; unexpected storage or
  programming failures still propagate instead of being broadly suppressed.
- Memory-curator cursors are now strictly validated and written atomically.
  Corrupt shape, thread identity, or message counts stop the curation run with
  a payload-safe diagnostic instead of silently resetting to zero and
  replaying already processed conversation history.
- REPL dynamic completion and input-history persistence failures are now
  observable degraded events; they no longer fail silently or discard a line
  already accepted through the builtin input fallback.
- Interactive `:history` now distinguishes an empty thread from malformed or
  unreadable persisted state, and daemon chat timeout lookup no longer hides
  unexpected configuration loader failures behind the 120-second default.
- Daemon reason-output recovery now validates typed manifest/progress state
  before composition, skips terminal jobs, reports corrupt manifests and
  optional progress explicitly, and schedules a retry only after the updated
  attempt state is durably persisted.
- Repository collection reads now isolate malformed records and emit
  payload-safe `record_decode_failed` warnings with collection and recoverable
  record identity. Healthy memory, candidate, source, profile, persona, reason,
  reflection, notification, and trace records remain readable; malformed
  file-backend JSON is diagnosed at the storage boundary instead of silently
  disappearing before repository validation.
- Audit logging and memory/persona thought-trace recording no longer swallow
  secondary failures silently. They now use one observable best-effort
  boundary that writes a structured degraded event and falls back to a Python
  warning if the structured log sink is unavailable, without failing the
  already-successful primary operation.
- Daemon request handling no longer hangs the client on an unexpected error. Any
  failure that is not a `ProtocolError` (e.g. a non-chat request raising) is now
  caught at the connection boundary, logged as `daemon/request_failed`, and returned
  as a failed response carrying the compact exception chain, instead of killing the
  handler thread and leaving the client blocked until its socket timeout.
- Guarded the daemon export-retry timer list with a lock and prune already-fired
  timers, fixing a shutdown-time race and unbounded growth over long uptime.
- The macOS notification adapter now applies a 10s timeout to `osascript`, so a hung
  system dialog can no longer block the notification-delivery loop indefinitely.
- SQLite v1 databases now preserve and expand every legacy `payload` object
  during the v2 schema migration, create a pre-upgrade backup, and roll back the
  schema version on failure instead of dropping user data.
- Reason step and thread updates now use a real SQLite transaction, so a failed
  second write rolls back the whole reasoning advance.
- Cached default storage backends are now scoped by project root and closed
  when reset, preventing one process from accidentally reusing another
  workspace's database.
- Daemon memory-curator, reflection, reason, export, and notification workers
  now retain health state and keep their owning loops alive after unexpected
  per-iteration exceptions.
- Removed the unused in-memory reflection event queue and obsolete post-turn
  reason proposal callback, neither of which affected active behavior.

## v0.2.5 - 2026-06-20

### Added

- Added `nuself pack` command group for thought pack management:
  - `pack export <name>` — copy `private/nuself.sqlite` to `private/exports/<name>.sqlite`.
  - `pack import <path>` — copy a `.sqlite` file into `private/imports/` for browsing.
  - `pack inspect [<name>]` — show table and item counts for a pack (resolves `imports/`, then `exports/`, then literal path; defaults to main database).
  - `pack list` — list imported and exported packs with file sizes.
- Simplified thought pack format to direct `.sqlite` copies (removed `.tar.gz` / `.jsonl` plan from spec).

### Changed

- `SqliteStorageBackend.__init__` now auto-creates parent directory for the database path.
- Updated `docs/spec/storage-v2.md` to reflect simplified thought pack design.

## v0.2.4 - 2026-06-04

### Added

- Added `StorageBackend` / `StorageCollection` protocol abstraction — all repositories now accept a unified backend instead of direct file I/O.
- Added `FileStorageBackend` — wraps existing `private/` directory layout behind the protocol, zero data migration.
- Added `SqliteStorageBackend` — SQLite-backed implementation with dynamic columns (every top-level key becomes its own column for browsability).
- Added `auto_backend()` — automatically selects SQLite when `private/nuself.sqlite` exists, otherwise falls back to file system.
- Added `nuself dev migrate` — migrates all data from file system to SQLite.
- Added `nuself dev db-schema` — shows database table structures.
- Added `nuself dev storage` — shows current active backend and data counts.
- Added `SqliteStorageBackend.close()` — WAL checkpoint + connection close on shutdown.
- Added SIGTERM/SIGINT handlers in daemon — graceful shutdown via `shutdown_requested` event instead of `os.kill`.
- Added thread timeout logging — background threads that fail to stop within 5s are logged as warnings.
- Added export timer tracking — `threading.Timer` objects are cancelled on daemon shutdown; remaining queue items are drained and logged.

### Changed

- `PrivateWorkspaceStore` no longer eagerly creates `private/nuself.sqlite` on `ensure()` — database is created lazily by `SqliteStore` on first use, fixing a race where `auto_backend()` could switch to SQLite mid-operation.
- All repository constructors now default to `auto_backend()` instead of `create_file_backend()`.
- `_FileCollection.list()` uses `rglob("*.json")` instead of `iterdir()` — finds old nested step files (`steps/{tid}/{sid}.json`) during migration.
- Background thread join timeout increased from 1s to 5s.
- Interactive chat Ctrl-C no longer exits the REPL — cancels current turn and returns to prompt. Ctrl-D (`EOFError`) still exits.

### Removed

- Removed `atexit.register(self.close)` from `SqliteStorageBackend` (caused database corruption when background threads wrote during atexit shutdown).
- Removed `_initialize_workspace_schema` from `PrivateWorkspaceStore` — table creation deferred to `SqliteStore`.
- Removed `memory_relations` from `COLLECTION_NAMES` and `COLLECTION_DIR_MAP` (dead collection — relations are computed from entries).
- Removed `reindex()` side effects — all `reindex()` methods are no-ops returning `Path("_reindexed_")`; derived index files (`memory_index.json`, `profile_index.json`, `source_index.json`, `relation_index.json`, `symbolic_graph.json`) are no longer written.
- Removed file caching from `MemoryEntryRepository` relation index and symbolic graph methods — they compute from `self.list()` in real time.

## v0.2.3 - 2026-06-04

### Added

- Added `docs/spec/storage-v2.md` — three-phase storage abstraction plan (protocol → SQLite → thought packs).

### Changed

- Storage layers refactored behind the `StorageBackend` protocol. All repositories now accept `backend: StorageBackend | None` and default to file-backed storage.
- `PersonaPromptRepository` refactored to support dual mode: global via `StorageBackend` or legacy thread-scoped via `root` path.
- `ProfileItemRepository`, `ReflectionRepository`, `NotificationOutbox`, `SourceRepository`, `MemoryEntryRepository`, `MemoryCandidateRepository`, `TraceRepository`, `ReasonRepository` all ported to `StorageBackend`.
- Steps stored flat by `step.id` (no `{thread_id}/` subdirectory) — `list_steps(thread_id)` uses `collection.find(thread_id=...)`.
- `get_step(step_id)` improved from O(n) directory scan to O(1) key lookup.

### Removed

- All module-level file I/O helpers (`_write_json_atomic`, `_safe_read_*`, `_validate_id`) from individual repositories — centralized in `storage.py`.

### Added

- Added `StorageBackend` / `StorageCollection` protocol abstraction — all repositories now accept a unified backend instead of direct file I/O.
- Added `FileStorageBackend` — wraps existing `private/` directory layout behind the protocol, zero data migration.
- Added `SqliteStorageBackend` — SQLite-backed implementation with dynamic columns (every top-level key becomes its own column for browsability).
- Added `auto_backend()` — automatically selects SQLite when `private/nuself.sqlite` exists, otherwise falls back to file system.
- Added `nuself dev migrate` — migrates all data from file system to SQLite.
- Added `nuself dev db-schema` — shows database table structures.
- Added `nuself dev storage` — shows current active backend and data counts.
- Added `SqliteStorageBackend.close()` — WAL checkpoint + connection close on shutdown.
- Added SIGTERM/SIGINT handlers in daemon — graceful shutdown via `shutdown_requested` event instead of `os.kill`.
- Added thread timeout logging — background threads that fail to stop within 5s are logged as warnings.
- Added export timer tracking — `threading.Timer` objects are cancelled on daemon shutdown; remaining queue items are drained and logged.

### Changed

- `PrivateWorkspaceStore` no longer eagerly creates `private/nuself.sqlite` on `ensure()` — database is created lazily by `SqliteStore` on first use, fixing a race where `auto_backend()` could switch to SQLite mid-operation.
- All repository constructors now default to `auto_backend()` instead of `create_file_backend()`.
- `_FileCollection.list()` uses `rglob("*.json")` instead of `iterdir()` — finds old nested step files (`steps/{tid}/{sid}.json`) during migration.
- Background thread join timeout increased from 1s to 5s.
- Interactive chat Ctrl-C no longer exits the REPL — cancels current turn and returns to prompt. Ctrl-D (`EOFError`) still exits.

### Removed

- Removed `atexit.register(self.close)` from `SqliteStorageBackend` (caused database corruption when background threads wrote during atexit shutdown).
- Removed `_initialize_workspace_schema` from `PrivateWorkspaceStore` — table creation deferred to `SqliteStore`.
- Removed `memory_relations` from `COLLECTION_NAMES` and `COLLECTION_DIR_MAP` (dead collection — relations are computed from entries).
- Removed `reindex()` side effects — all `reindex()` methods are no-ops returning `Path("_reindexed_")`; derived index files (`memory_index.json`, `profile_index.json`, `source_index.json`, `relation_index.json`, `symbolic_graph.json`) are no longer written.
- Removed file caching from `MemoryEntryRepository` relation index and symbolic graph methods — they compute from `self.list()` in real time.

## v0.2.2 - 2026-06-02

### Added

- Added persona management through unified handle panel: `persona list` now shows
  `[0]`, `[1]` visible index markers; new `persona create <name> <prompt>`,
  `persona disable <handle>`, `persona enable <handle>` CLI/REPL commands.
- Added `:persona` / `:p` REPL command for managing personas without leaving the
  chat session (supports list, show, create, delete, disable, enable).
- Added `persona_disable` and `persona_enable` agent tools (chat + reason);
  `persona_list` now excludes disabled personas by default; `persona_think`
  rejects disabled personas with a clear error.
- Added `persona_disabled` / `persona_enabled` trace kinds and recording.
- Added `persona delete` batch support: `nuself persona delete 0,2-4` deletes
  multiple personas at once.
- Added TUI renderers for persona prompts (`tui/persona.py`): terminal-width
  detection, text wrapping, `[persona]` tag in magenta, name in orange.
- Added `docs/spec/persona/management.md` — full design spec for persona
  management via handles.
- Added `docs/spec/hardcode.md` — central registry of all non-configurable
  numeric constants across the codebase.

### Changed

- `PersonaPrompt` gains a `disabled: bool = False` field (backward-compatible
  via `from_wire` default); `PersonaPromptRepository.set_disabled()` added.
- `persona show` and `persona delete` now accept visible index handles in
  addition to name or id.
- Persona list/show output now uses `render_record_block` format with colored
  tags, wrapped text, and formatted timestamps (same style as memory entries).
- `trace/service.py record_reason_thread_created`: evidence_refs is now `[]`
  instead of passing the thread's accumulated evidence_refs (trace evidence
  should reflect this trace event, not the thread's lifetime).
- `trace/service.py record_reason_step`: decision_points now uses the step's
  `terminal_status`/`terminal_reason` instead of `step.delta`.
- `Spec/reason.md`: thread/step ID format corrected to
  `reason-{timestamp}-{uuid[:8]}` / `step-{timestamp}-{uuid[:8]}`.
- `reason/domain.py ReasoningThread.to_wire()`: field order aligned with spec
  (active_items before evidence_refs, reasoning_prompt inlined).
- `reason/__init__.py`: exported `TerminalStatus` (was missing from `__all__`).
- `trace/domain.py`: added `persona_disabled` and `persona_enabled` to
  `TraceKind` literal and `TRACE_KINDS` tuple.

### Removed

- `MAX_ACTIVE_THREADS = 5` cap removed. Reason thread creation already requires
  user approval, making the artificial limit unnecessary. Agent tool
  `reason_propose` no longer enforces a thread count check.

## v0.2.1 - 2026-06-02

### Added

- Added cooperative file-level locking (`.lock`) to prevent concurrent writes to the same export job from the daemon worker and CLI.
- Added daemon startup reconciliation: workspaces are scanned for non-complete job manifests and stale `.lock` files are cleaned up on worker start.
- Added the first `reason` output-composition infrastructure: export jobs now plan and persist manifests, chunks, progress, and combined Markdown artifacts inside the owning reason workspace, and the chat tool registry exposes `reason_export`.
- Added `scripts/mdpdf.sh` to convert one or more Markdown files into PDFs with pandoc and xelatex for easy manual sharing.

### Changed

- Export queue moved from filesystem directories (`queue/`, `processing/`, `failed/`) to a daemon-global in-memory `queue.SimpleQueue` event bus. The `manifest.json` is the sole source of truth; queue events are purely in-memory signals. This eliminates partial writes, stale processing claims, duplicate event files, and 80+ lines of file-management code from the daemon worker.
- Export worker no longer polls at a fixed interval. It blocks on the in-memory queue and processes jobs as soon as they arrive, with `threading.Timer` for scheduled retries. The `DaemonExportWorkerConfig` and its `interval_seconds` setting have been removed.
- Export jobs now live under `export/jobs/{job_id}/` instead of the flat `export/` root, so re-planning with different parameters no longer destroys pending work for other jobs.
- Queue event schema removed entirely (in-memory only). The worker reconstructs job paths from `thread_id` and `job_id`.
- `plan_job` pushes to an in-memory callback instead of writing file-based queue events.
- `_clear_job_artifacts` no longer preserves `queue/`/`processing/`/`failed/` subdirectories.
- Startup reconciliation now scans workspace manifests instead of a file-based processing directory. Incomplete manifests are re-enqueued to the in-memory queue.
- Reason exports now persist a deterministic section plan derived from source content, so chunk size no longer determines chapter boundaries.
- Reason exports now automatically generate a PDF from the final combined Markdown artifact after composition completes.

### Fixed

- `scripts/mdpdf.sh` now sets a CJK-capable default font pair and `zh-CN` metadata so Chinese Markdown renders correctly in the generated PDF.
- Approval-gated tool prompts now emit a visible live REPL log line before waiting for confirmation input, so the prompt is obvious before the user enters `y` or `n`.
- Reason thread proposals now use the decorated `reason_propose` tool wrapper for confirmation instead of a post-turn CLI prompt, while `proposal_created` remains available as an audit log event.
- Reason export now has a dedicated agent skill that tells chat to call `reason_export` directly and read the approval-gated JSON result instead of treating export as a separate confirmation turn.
- `plan_job` no longer uses `_clear_directory` (rmtree on the entire export root), which destroyed pending work when re-planning with different parameters. Job artifacts are now cleaned per-job under `jobs/{job_id}`.

## v0.2.0 - 2026-05-29

### Added

- Added LLM endpoint failover so NuSelf can switch between configured LLM endpoints when an account/subscription endpoint becomes unavailable, with OpenAI-compatible endpoints as the default and `anthropic: true` for Anthropic endpoints.
- Added the trace foundation with `ThoughtTrace`, `TraceLink`, file-backed trace storage, trace search, CLI `trace list/show/search`, and REPL `:trace` commands.
- Added automatic `chat_turn` trace recording when final chat replies cite evidence references.
- Added REPL `:restart` / `:r` for restarting the daemon and reconnecting without leaving the interactive session.
- Added the long-run reason foundation with file-backed reasoning threads, reasoning steps, `nuself reason ...` commands, and REPL `:reason` commands.
- Added generic private workspaces with per-owner SQLite scratch storage, first used by reason threads.
- Added `reason watch` for continuously polling a reasoning thread and rendering new steps incrementally.
- Added background reason scheduling with `ReasonAdvancer`, `ReasonScheduler`, daemon config, and per-thread `skip_next_advance_until` cooldown.
- Added topic-specific reasoning prompts and the `reasoning_prompt_gen` tool so a separate prompt-generation agent/tool can adapt the shared reason step schema to writing, investigation, design, planning, debate, and other topic types.
- Added explicit `ReasoningStep.tool_logs` snapshots for tools used during reason advances, rendered through the same `service_tool_called` log renderer used by chat and other subsystems.
- Added chat-based reason proposal through the turn-confirmation protocol; `reason_propose` creates a pending proposal and the CLI asks for confirmation before starting a thread.
- Added reflection organization for merging similar pending reflection ideas, including `nuself inbox reflection organize`.
- Added reflection promotion into long-run reason threads with trace provenance.
- Added read-only reason and trace tools for chat, with Agent Skills that tell the agent when to consult them.

### Changed

- Chat prompts now treat agent-facing services as tools plus skills, so memory and reflection tools include explicit usage policy instead of appearing only as optional commands.
- Chat service skills now live in flat Agent Skill Markdown files instead of hard-coded prompt strings.
- Reason proposal policy now lives in a separate `reason_proposal` skill, while the main `reason` skill is read-only.
- Service/tool calls now log caller and callee tags, such as `[chat] [memory]`, while preserving the existing key/value log format.
- Chat agent tools now register only through LangChain `StructuredTool` objects, with the old NuSelf chat-tool protocol removed and the same loaded tool list visible in ordinary and persona-synthesized response prompts.
- Reason is now generalized around `topic`, free-text tracked items, mandates, structured step `output`, and generated topic-specific prompts over one shared reasoning structure instead of hard-coded hypothesis/question fields.
- Reason advance now uses one LangGraph `create_agent` path with tools and `ReasonStepOutput` structured output instead of silently falling back to raw LLM completion, placeholder steps, or legacy compatibility behavior.
- `reason_propose` now requires `active_items` and `mandates`, and no longer accepts arbitrary chat-provided `evidence_refs`.
- `reason show` and `reason watch` now render complete thread headers and step bodies, including `mandates`, `reasoning_prompt`, evidence, `output`, `delta`, tracked-item updates, confidence, and tool logs.
- Reorganized CLI and REPL commands around the v0.2.0 command model, moving sources under `memory source`, proactive items under `inbox`, diagnostics under `dev`, and removing old command-path compatibility aliases.
- Replaced `readline` with `prompt_toolkit` for interactive input, styled prompts, persisted history, and tab completion.
- CLI and REPL list views now use consistent 0-based visible indexes; object commands accept numeric handles directly; and memory delete/review accept/reject support compact batch index selections such as `1,3-5,9`.
- CLI command help now describes top-level commands and command-group actions, including nested memory and inbox groups.
- Memory list/detail output now follows the shared record-block style with `[memory] [index] key=value` headers, lightly colored key/value values, and indented text bodies.
- Memory preview now follows the same record-block style as memory list while omitting visible operation indexes.
- Memory curator actions now require explicit tags for create/update candidates, and manual memory intake no longer creates heuristic fallback entries when LLM inference fails.
- Reflection no longer blocks new cycles based on pending reflection count; duplicate pressure is handled by organization instead.
- Competitive persona discussion logs now render as `[selves]` activity, and visible discussion notes follow the configured chat language preference.
- `[selves]` logs now render `status` as indented body text and avoid repeating `escalation_reason` in the header, so long activation text does not stretch the header.
- Persona/self activity output now uses structured logs only, so REPL rendering keeps log headers and body text in the same format as other activity logs.

### Fixed

- Fixed REPL chat retry idempotency so daemon timeouts retry the same logical turn, avoid duplicate persisted user inputs, and reuse already-completed turn results instead of rerunning persona work.
- Clarified LLM endpoint logs so exhausted endpoints are distinguished from actual failover attempts.
- Fixed reason step validation so missing structured `output` is rejected.
- Fixed reason tool rendering so captured tool results are not truncated by the middleware before being persisted on `step.tool_logs`.
- Fixed reason thread creation so prompt-generation failures surface as errors instead of persisting a thread with `(not generated)`.
- Fixed `reason_show` chat tool to accept `current` as an alias for the most recent active thread.
- Removed name-prefix matching for tool service components; `StructuredTool.metadata["service_component"]` is now the source of truth for `service_tool_called` rendering.
- Fixed memory update trace coverage for curator auto-accept and manual memory operations.
- Fixed reason logs to use the configured project root.
- Fixed `:reason` with no arguments to show reason command help instead of listing threads.
- Fixed notification deep links so thread IDs and query values round-trip with reserved URL characters.
- Fixed chat-confirmed reason proposals so prompt generation uses the resolved project root when the CLI was started without `--project-root`.
- Fixed background reason advances that use concurrent tools by serializing persona prompt and trace index writes, and keeping scheduler failures logged without killing later scheduling.
- Fixed reason pacing prompts so round-based simulations and debates advance at most one complete round per step instead of skipping ahead through multiple rounds.
- Clarified service skills with explicit allowed tools, confirmation boundaries for mutating actions, and correct workspace value shape.
- Fixed `[workspace]` service tags in rendered tool logs so they use a valid 256-color ANSI foreground code.
- Reworked service tool logs to store structured `args`, `result`, and `error` metadata and render tool I/O from those fields.
- Unified tool `args` and `result` JSON rendering so both use the same pretty-printed block format.
- Restored argument/result rendering for already persisted reason tool logs that still store tool I/O in the legacy message body.
- Changed service tool log headers to show the colored `tool=...` field before the colored `status=...` field.
- Tightened reason persona constraints so persona dialogue or judgments must be grounded by same-step `persona_think` calls instead of simulated directly in step output.
- Added `reason_context` and `reason_step` read tools for agent-facing reason inspection, and omitted tool logs from agent-facing reason read outputs.
- Added structured reason terminal recommendations so advances can automatically resolve or pause threads without parsing step prose.
- Changed agent-facing reason read tools to return JSON strings instead of terminal-formatted text.
- Added trace artifact lookup with `nuself trace related <artifact_ref>`, `:trace related <artifact_ref>`, and the read-only `trace_related` agent tool; artifact deletion keeps provenance traces instead of cascading through trace records.

### Docs

- Planned v0.2.0 around a breaking command cleanup, long-run reasoning, and traceable thought provenance.
- Finalized the reason spec around generalized topics, structured step output, explicit tool logs, complete rendering, and reflection organization behavior.

## v0.1.0 - 2026-05-16

Initial development baseline.

### Added

- CLI and daemon runtime with lifecycle commands, socket protocol, daemon-backed chat, attach/open flows, health/status commands, and structured local logs.
- Interactive REPL with thread switching, command help, Markdown rendering, typewriter-style NuSelf replies, readable activity logs, transcript export, clipboard support, and automatic transcript saves on exit.
- Private file-backed memory system with entries, candidates, profile items, source ingestion, search, stats, symbolic relations, graph traversal, curation, optimization, and review workflows.
- LangGraph-backed conversation runtime with memory/source retrieval, structured answer metadata, tool handling, unsupported-claim guard, and deterministic fallback behavior when no LLM API is configured.
- Lightweight internal selves/persona system with activation, competitive discussion, stable self colors in logs, and synthesized user-facing answers.
- Presentation agent stage that separates internal draft reasoning from final user-facing prose and retries when protocol or persona internals leak into replies.
- Proactive reflection scheduler with candidate generation, LLM relevance gate, persona discussion, pending limits, cooldowns, quiet hours, daily caps, and notification handoff.
- Notification outbox with log-only, macOS, and email adapters, delivery loop, watch commands, status filtering, and deep links.
- Unified YAML configuration, effective-config inspection, runtime path conventions, and private data isolation under `private/`.
- Long-run reasoning design and TODO spec for future durable reasoning threads.
- Versioning discipline with `CHANGELOG.md`, release checklist, and `nuself --version`.

### Fixed

- Prevented raw structured response JSON and protocol fields from appearing in normal chat replies.
- Preserved persona and reflection activity logs in transcript exports using human-readable formatting.
- Interleaved transcript logs with the chat turns that produced them instead of appending all logs at the end.
- Kept REPL open across chat daemon timeouts with one retry while preserving logs from failed attempts.
- Rendered human-facing timestamps in the current system timezone while preserving UTC-style internal timestamps and filenames.

### Docs

- Added behavioral specs for CLI interaction, memory, reflection, notifications, persona discussion, logging, configuration, presentation, chat tools, versioning, and long-run reasoning.
