# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

In progress — continuously audit and simplify while preserving composability.

## Current Phase

Continue removing convenience composition wrappers that obscure the live
thread-aware capability provider.

## Constraints

- Preserve domain-owned registries, semantic validators, service APIs, durable
  recovery, and the single-scheduler daemon.
- Add no generic bus, facade hierarchy, compatibility shim, worker, or lock.
- Keep each reduction independently tested and committed; do not return this
  board to Idle while the persistent review goal remains active.

## Phase Evidence

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
- Memory add/search/reindex, source delete/extract, system status, and REPL
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
