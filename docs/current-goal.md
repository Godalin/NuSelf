# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

In progress — continuously audit and simplify while preserving composability.

## Current Phase

Audit the 371-line CLI composition root for separable parser, dispatch, and
interactive-chat policy. Preserve its one-root lifecycle role; extract only
concerns with independent consumers or dependency direction.

## Constraints

- Preserve domain-owned registries, semantic validators, service APIs, durable
  recovery, and the single-scheduler daemon.
- Add no generic bus, facade hierarchy, compatibility shim, worker, or lock.
- Keep each reduction independently tested and committed; do not return this
  board to Idle while the persistent review goal remains active.

## Phase Evidence

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
- Scheduler task, submission, completion, active identity, and busy-resource
  state remain necessary for coalescing and serialization. Four lifecycle
  booleans were replaced by one monotonic `created/running/stopping/stopped`
  phase; running and accepting health now derive from that source.
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
  importance mutation share one composed repository and index-refresh policy.
- Agent tools now receive only `MemoryService`; the parallel entry-repository
  capability and duplicated save/reindex mutations are gone. Curator, source,
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
