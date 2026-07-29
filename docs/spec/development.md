# Development Process Spec

## Code Standard

- Standard Python project managed by `uv`.
- Type-check with `uvx pyright`.
- Sub-components must be individually tested.
- Packages imported directly by runtime modules must be declared as direct
  project dependencies rather than relying on another dependency to install
  them transitively.
- Built wheel smoke tests must install the artifact into a clean environment
  and import the CLI/runtime boundary.
- User-facing changes must update both `README.md` and `README.zh-CN.md`.
- Use [`../current-goal.md`](../current-goal.md) as the single active execution
  board and [`../TODOs.md`](../TODOs.md) for unresolved backlog.

## Branch Strategy

- `main` is the stable, releasable branch.
- `dev/v0.3.x` is the active optimization branch for the current minor line.
- `feature/*` branches are isolated experimental work for a single feature or fix.
- Each `feature/*` branch should merge back into `dev/v0.3.x` before anything is promoted toward `main`.
- Release work should land on the stabilization or stable branch first, then be tagged from the release commit.
- CI runs for pushes to `main` and every `dev/**` development branch. Pull
  requests targeting either `main` or `dev/**` run the same validation matrix,
  so ordinary development is verified before and after integration rather than
  only when promoted to the stable branch.
- Repository-owned workflows use maintained GitHub-hosted action generations
  that run on the current Node action runtime. CI and release must not retain an
  action major that GitHub reports as runtime-deprecated.

## Commit And Push Policy

- Keep commits separated by functional boundary. Governing specs, tests,
  changelog entries, and progress-state updates belong in the same commit as
  the behavior they describe; do not create a second documentation-only commit
  that temporarily allows drift.
- Before non-trivial work, check `docs/current-goal.md`. Mention conflicts before proceeding.
- Before implementation begins, update `docs/current-goal.md` so its objective,
  ordered work, exclusions, and completion evidence govern the intended change.
- Update progress immediately when a step completes or the active scope
  changes. Commit the relevant progress update with the functional change.
- When the objective is complete, move only unresolved follow-ups to
  `docs/TODOs.md`; preserve completed history in Git or `CHANGELOG.md`, then
  return `docs/current-goal.md` to an explicit idle state.
- Push normal development commits only when the user asks to publish or sync the branch.
- Before pushing, confirm the working tree is clean and the intended commits are on the current branch.
- Normal branch push command: `git push`.
- If a release tag was created, push the release commit and tag together: `git push && git push origin v<version>`.

## Release And Tag Policy

Versioning and changelog rules live in [`versioning.md`](versioning.md). Release work must follow that spec plus this concrete flow:

1. Finish and verify all intended functional commits.
2. Move relevant `CHANGELOG.md` `Unreleased` entries into a dated version section and create a fresh empty `Unreleased` section.
3. Bump `pyproject.toml` to the release version. Runtime `nuself.__version__` must continue to resolve to the package metadata version.
4. Run `uv run pytest`, `uvx pyright`, and `git diff --check`.
5. Confirm `uv run nuself --version` prints the intended version.
6. Commit the release metadata with message `release: <version>`.
7. Create an annotated git tag: `git tag -a v<version> -m "Release <version>"`.
8. Push the release commit and tag together when the user asks to publish: `git push && git push origin v<version>`.

Do not tag unreleased feature commits directly. Tags mark release commits only.

## Development Style

- **Design before implement**: For any non-trivial feature or behavioral change, write or update the relevant spec document **before** writing implementation code.
- **Spec is authoritative**: A feature change is not complete until the spec that governs it is updated in the same change.
- **No spec drift**: If code behavior diverges from its spec, either fix the code or update the spec. The spec must always describe the actual system.
- Active development favors the clean target architecture over incremental
  compatibility. Rename, move, or replace internal APIs through one
  repository-wide migration; do not retain forwarding imports, deprecated
  aliases, parallel protocols, legacy base classes, or dual write/read paths
  unless an external persisted-data or wire migration is explicitly specified.
- Interface changes must update all callers, tests, examples, and docs in the same commit.
- Configuration shape changes must update `docs/spec/config.md`, `docs/nuself-config.schema.json`, `examples/private/config.yaml`, and relevant config tests in the same change.
- Do not preserve obsolete CLI commands, protocols, schemas, or APIs unless a document explicitly requires them.
- Refactors are welcome when they clarify architecture; always pair them with doc and test updates.
- Keep `docs/current-goal.md` concise: one active objective, ordered next steps,
  out-of-scope boundaries, and completion evidence.
- Keep `docs/TODOs.md` limited to unresolved medium/long-term backlog. Completed
  user-visible work belongs in `CHANGELOG.md`; completed internal work remains
  discoverable through Git history.
- `docs/architecture.md` explains current system boundaries and rationale but
  must not duplicate behavioral contracts from `docs/spec/`.
- Keep scoped implementation constraints in local `AGENTS.md` files near the code, not the root README.

### Shared Time Boundary

- Generic UTC clock helpers live in `nuself.clock`, never in a domain module.
  `utc_now()` returns an aware UTC `datetime`; `utc_now_iso()` is the shared
  producer for persisted ISO-8601 timestamps. Domains may keep specialized ID
  or scheduling helpers, but must compose them from the neutral clock.

### Shared Atomic File Boundary

Runtime JSON and text state uses `nuself.storage.write_json_atomic()` or
`write_text_atomic()`. The shared writer creates a unique sibling temporary
file, writes and `fsync`s its complete content, atomically replaces the
destination, then `fsync`s the parent directory. Success means both file
content and the replacement directory entry reached the operating system's
stable-storage boundary.

NuSelf-owned runtime state is private by default. Dependency-neutral helpers
in `nuself.private_fs` create or harden owned directories to owner-only `0700`
and owned files to `0600`. Atomic writers, SQLite databases and internal
snapshots, append-only logs, lock files, and other internal append streams all
use that boundary. Sensitive content must never exist in a
broader-permission file, even briefly.

A write, file-sync, or replace failure remains the propagated exception when
temporary cleanup succeeds or the temporary file is already absent. Cleanup
also runs for `BaseException` interruptions. If cleanup itself fails,
`AtomicWriteCleanupError` exposes both `primary_error` and `cleanup_error`,
names the residual temporary path, and uses the primary persistence error as
its explicit cause. Cleanup must not mask the authoritative failure, and the
residual artifact is not silently reported as removed.

After replacement, the temporary pathname is no longer owned and must never be
cleaned. If parent-directory synchronization then fails,
`AtomicWriteDurabilityError` reports that the new destination is
process-visible but its crash durability is uncertain; its `sync_error` is the
explicit cause. The shared writer performs no hidden write, sync, replace, or
cleanup retry.

`write_json_atomic()` validates and serializes the complete payload as strict
JSON before creating its temporary file. Non-string mapping keys, arbitrary
objects, and non-finite floats fail without touching the destination or
creating a temporary artifact.

Subsystems must not define parallel atomic writer helpers or use a fixed
`.tmp` path. Direct `Path.write_text()` remains appropriate only for an
explicit user-selected artifact whose partial-write and permission behavior is
documented, or inside the shared writer after it securely creates the
temporary file.

An explicitly user-selected external export is not a NuSelf-owned runtime
path. Its parent directory and resulting mode continue to follow the user's
filesystem and `umask`; internal helpers must not silently chmod that external
directory.

### Import Placement Policy

Module-level imports are the default for domain models, repositories, services,
renderers, and reusable helpers. Function-local imports are limited to these
composition boundaries:

- optional integrations whose dependencies may not be installed;
- `TYPE_CHECKING`-guarded imports used only for annotations;
- CLI command handlers and daemon/background-worker factories that deliberately
  defer loading a heavy subsystem until the command or worker is used;
- a documented cycle boundary where moving the import would create an actual
  package initialization cycle.

Local imports must not be used merely to hide an unclear dependency. Repeated
imports of ordinary lightweight modules belong at module scope. New local
imports outside the allowed boundaries require a nearby comment stating the
optional dependency, deferred-loading reason, or cycle being avoided.

## Framework-Native Agent Architecture

NuSelf uses LangChain/LangGraph as the agent infrastructure layer. When the framework has a current recommended API for an agent concern, NuSelf must use that API rather than maintain an equivalent private protocol.

Rules:

- Tool calling must use LangChain tool objects and model/agent tool-calling APIs such as `bind_tools(...)` or `create_agent(..., tools=[...])`. Models must not be asked to print ad-hoc visible markers or NuSelf-only tool-call text.
- Structured agent output should use LangChain structured-output mechanisms where practical, such as `create_agent(..., response_format=...)` or provider/tool strategies. Prompted JSON may remain only as a bounded fallback for non-agent subsystems until they are migrated.
- Stateful agent workflows should use LangGraph state graphs or LangChain agents/middleware. NuSelf may own domain state and persistence, but should not duplicate framework runtime concepts.
- Agent skills, middleware, model invocation, retries, tool execution, and message passing should follow current LangChain documentation. Any deliberate deviation must be documented in the relevant spec with a reason and a migration path.
- Custom code should focus on NuSelf domain semantics: memory, reflection, reason, trace, private storage, rendering, and logs.
- Framework middleware owns completed tool outcomes. Domain adapters may resolve
  service metadata and project those outcomes, but decorators and tool
  implementations must not create parallel tool-execution audit events.
- Approval wrappers own approval intent and decision records only. They must
  not duplicate the middleware-owned completed tool outcome.
- Shared approval audit definitions are sealed before runtime use. The wrapper
  supplies only schema data; fixed message, level, status, error, duration, and
  failure-diagnostic policy belong to the approval audit adapter.

## Subsystem Service Architecture

NuSelf is a multi-subservice system. Major domains such as memory, reflection, notification, trace, and reason should be implemented as clear subsystems rather than as incidental CLI helpers.

Each subsystem should expose these layers when the domain is non-trivial:

1. **Domain models**: typed records and validation rules.
2. **Repository**: file-backed persistence and rebuildable indexes.
3. **Service**: user-intent operations and policy decisions.
4. **Renderer**: human-readable CLI/REPL presentation.
5. **Tool-facing adapter**: a small interface suitable for use by chat, reason, reflection, or future agents.
6. **Agent skill**: prompt-level policy that tells agents when and why to use the subsystem's tools.

Rules:

- Agents should call service/tool-facing interfaces, not read or write subsystem storage files directly.
- CLI and REPL commands should be thin wrappers over service methods when behavior is non-trivial.
- Cross-subsystem effects should be explicit. For example, reason may call trace recording through `TraceRecorder`, not by constructing private trace files itself.
- Tool-facing interfaces must use small typed inputs and outputs, avoid leaking raw file paths unless intentionally requested, and be safe to expose to LLM-driven agents.
- Tool-facing interfaces define capability; agent skills define usage policy. A service exposed to agents should usually provide both.
- Agent skills must be explicit about when tool use is expected, when it is optional, and what claims are invalid without a tool result.
- Shared renderers should be reused so CLI, REPL, transcripts, and logs stay consistent.

## Handler Composition

`runtime.handlers.HandlerRegistry` is the shared keyed synchronous dispatch
primitive. Registration and middleware composition are mutable build-time
operations. `seal()` is the one-way transition to runtime use: it compiles
every middleware chain once into a stable dispatch table. `dispatch()` rejects
an unsealed registry, so callers cannot observe a partially composed handler
set or middleware stack. Sealed registries reject all later registration and
middleware changes.

Registries backed by a closed protocol or command catalog call
`seal(expected_keys=...)`. The shared registry compares the complete key set
before publishing its dispatch table and raises
`HandlerRegistryCoverageError` with immutable missing and extra key sets.
Daemon and REPL composition must not duplicate catalog coverage checks.

Handlers and middleware, including constructor-provided middleware, must be
callable and are rejected with `TypeError` at their composition boundary.

Caught exceptions must never be rendered locally with `str(exception)` or
f-string interpolation. Diagnostic output, fallback text, wrapping messages,
tool results, and persisted fields use
`diagnostic_exception_message(...)`. Control-flow classification that must
inspect the original message uses `safe_exception_message(...)` and retains the
original exception object. Existing string output such as subprocess stderr is
sanitized with `redact_sensitive_text(...)` before diagnostic persistence.

`resolve()` exposes the directly registered handler only before sealing for
composition-time inspection. It raises `HandlerRegistrySealedError` after
sealing; runtime callers use `dispatch()` so middleware cannot be bypassed.
Middleware order is outer-to-inner registration order, and wrappers must
preserve the original handler exception identity unless the middleware's
documented policy explicitly translates it.

Dispatch boundaries must distinguish registry lookup failure from an
invocation that raises the same exception type. A sealed closed-catalog owner
checks membership before dispatch when mapping an unknown key to a transport
response; it must not surround handler invocation with
`except UnknownHandlerError`, because that would relabel failures from
middleware, nested registries, or the handler itself.

The same rule applies to daemon `ProtocolError`. Socket envelope decode,
request-specific payload decode, and handler invocation use separate lexical
boundaries. Only a direct request payload codec failure is wrapped as
`DaemonRequestPayloadError` and translated by request dispatch. Raw
`ProtocolError` from later invocation preserves its identity and follows the
unexpected handler failure path.

Runtime event registration, publication, and filtered projection attachment
all use the same `(producer, name)` identity. New internal projections must
attach to all events intentionally or bind both fields; partial event-name
selectors are forbidden.

`EventPublisher.attach_projection(...)` is reserved for bounded synchronous
in-process projections whose completion deliberately belongs to publication.
Code requiring independent progress, network I/O, retries, or an unbounded wait
must own a bounded queue and worker lifecycle instead of attaching a callback
to the publisher.

Shared definition lookup is runtime-only: seal a `DefinitionRegistry` before
calling `resolve()` or injecting its semantic adapter into a runtime owner.
Composition-time inspection uses `definitions`; runtime owners must not retain
a registry that remains open to late registration.

Durable job wake-up owners use `runtime.jobs.JobAdmissionQueue` rather than raw
`queue.Queue` or `SimpleQueue`. Capacity, identity coalescing, in-flight
ownership, and explicit completion are shared transport mechanics; manifest
reconciliation and retry policy remain domain-owned.

Local job producers use a sealed `JobDefinitionRegistry.create(...)`; they do
not construct `JobMessage` fields directly. Queue ingress still validates
messages because decoded or externally supplied envelopes are untrusted.

Result-producing one-shot thread boundaries use `runtime.execution.OwnedCall`.
They must not reproduce ad hoc value/error boxes, daemonize authoritative work,
or leave a successfully started call unreaped on an exceptional exit path.

Process-local log delivery uses `project_log_events(...)` only for bounded
synchronous projections. Projection callbacks must not perform network calls,
retries, or unbounded waits. The logging core owns attachment identity and
reentrancy suppression; callers must not build parallel recursion guards.

Delayed callbacks use `runtime.scheduling.DelayedTaskScheduler` rather than
domain-owned `threading.Timer` collections. Domains supply stable identities,
delay values, callbacks, diagnostics, and recovery policy; the shared scheduler
owns atomic start rollback, completion removal, duplicate suppression, and
close/cancel lifecycle.

## CLI Module Boundaries

`nuself.cli` is a package whose `__init__.py` remains the composition root and
public entrypoint. Parser, command, and REPL implementations live beside it
under the same package.

- Importing the composition root must not replace process-global warning
  callables. A known third-party import warning may be filtered only with
  `warnings.catch_warnings()` around the exact dependency-owning adapter import,
  matching its full message and category. Other warnings remain caller-owned
  and visible.
- `cli/parser.py` owns top-level parser construction and accepts only dynamic
  chat launch-policy callbacks through `EntrypointHandlers`; it never imports
  `nuself.cli`.
- `cli/handlers.py` owns one-shot handler composition. `CliHandlerBindings`
  derives stable command keys from each parser's complete `prog`, registers
  the callable in one shared `HandlerRegistry`, and stores only the key in
  argparse defaults. After the parser tree is complete, the bindings seal the
  registry and attach it to the root parser.
- Parsed `argparse.Namespace` values never carry handler callables. Runtime
  dispatch reads the stable key and uses the sealed registry; missing,
  unsealed, duplicate, and unknown bindings fail through the shared handler
  errors rather than falling back to dynamic `callable(...)` checks.
- Help-only groups store no handler key and retain their selected parser for
  presentation. The single CLI dispatch boundary still rejects booleans and
  all non-integer exit statuses.
- Parser construction has no process-global handler registry. Repeated parser
  builds in tests or embedded callers compose independent sealed registries,
  including dependency-injected entrypoint controller methods.
- `cli/entrypoints.py` owns the launch policy for the default, `chat`,
  `attach`, and `open` entrypoints: daemon startup/selection,
  require-daemon handling, deep-link/thread preparation, and the choice
  between daemon-backed and local interactive sessions. It receives chat and
  REPL execution as typed callbacks from the composition root and does not
  implement either capability itself.
- `cli/chat.py` owns CLI-facing daemon and one-shot chat adapters: configured
  request timeout, transport/application error translation, correlated audit
  writes, direct `ConversationGraphRuntime` invocation, and post-turn memory curator
  coordination. `agent/chat/` remains the conversation domain/runtime; the CLI
  adapter only translates that capability to CLI result and output contracts.
- `daemon/request_handlers.py` owns typed request dispatch and response
  construction. Chat failure/completion and accepted-shutdown audit records
  resolve through `daemon/request_audit.py` and cannot replace the
  already-decided response or shutdown flag. Handlers do not choose request
  audit messages, levels, statuses, error policy, duration policy, or metadata
  shape.
- `daemon/transport_audit.py` owns the sealed socket read/dispatch/encode/write
  failure contract. `daemon/socket_server.py` owns transport control flow but
  never constructs failure log messages or projection defaults.
- `daemon/operations_audit.py` owns process cleanup and worker join-timeout
  diagnostics. It preserves ordered cleanup error records while server and
  supervisor owners retain control flow and exception propagation.
- `storage_audit.py` owns backend-close and outer CLI storage-cleanup audit
  schemas. Storage and CLI owners retain teardown control flow and exception
  aggregation but do not construct audit presentation.
- `daemon/audit.py` owns the immutable lifecycle event definition registry,
  exact per-event schema validation, and best-effort audit sink boundary.
- `runtime/definitions.py` owns generic sealed definition-registry mechanics.
  Runtime event and daemon audit registries adapt it without sharing semantic
  definition types or transport policy.
- `runtime/observability.py` owns the sealed secondary-failure taxonomy.
  Domain audit writers and event publishers provide only the failed primary
  identity; they never define local write/delivery failure event aliases.
  The same module owns the sealed terminal warning used when its structured
  sink is unavailable; callers never construct sink-failure warning strings.
- `agent/endpoint_audit.py` owns the sealed per-endpoint failover/exhaustion
  audit schemas for Chat, Memory, Persona, Reason, and Reflection.
  `agent/failover.py` retains control-flow ownership and supplies only the
  already-decided endpoint outcome plus safe endpoint identity fields.
- `agent/middleware.py` owns its sealed callback/reporter terminal-warning
  registry. Tool execution and capture supply only safe caught diagnostics and
  never construct warning presentation.
- `logs.py` owns its recursive-sensitive sealed infrastructure audit registry.
  Process-local observer delivery supplies only the caught exception; callable
  identity, presentation, schema, and terminal fallback remain logging-core
  policy.
- `runtime/warning_definitions.py` owns reusable sealed terminal-warning
  definition and rendering mechanics. `logs.py` composes its closed six-event
  taxonomy and supplies typed facts, never free-form warning strings.
- `daemon/lifecycle.py` owns the sealed raw process-log rotation warning
  contract. Startup supplies only the caught exception type and never
  constructs terminal warning presentation.
  `cli/daemon_lifecycle.py` owns shared observable start/stop/restart
  orchestration and typed transition projection for one-shot, launch, and REPL
  surfaces.
- `cli/daemon_status.py` owns shared status observation, safe failure rendering,
  and status-line formatting. `cli/commands/daemon.py` owns only daemon command
  handlers plus list/health presentation and exit decisions.
- `cli/commands/threads.py` owns one-shot thread list/show/create/rename/branch/archive
  lifecycle handlers; REPL thread switching remains in the REPL layer.
- `cli/commands/output.py` owns ANSI-aware printing and visible-handle error rendering
  shared by extracted command modules.
- `cli/commands/notifications.py` owns one-shot notification list/show/stats/watch/send/
  dismiss/clear handlers; notification REPL shortcuts remain in the REPL layer.
- `cli/commands/reason.py` owns one-shot reason list/show/start/action/delete handlers.
  The long-running terminal watch loop remains with REPL/session orchestration.
- `cli/commands/trace.py` owns one-shot trace list/show/search/related/reindex handlers
  and their command-line filter normalization.
- `cli/commands/reflections.py` owns one-shot reflection list/show/lifecycle/promote/
  organize handlers; reflection REPL shortcuts remain in the REPL layer.
- `cli/commands/persona.py` owns dynamic persona list/create/show/delete/enable/
  disable handlers and visible-handle resolution shared with persona REPL
  shortcuts.
- `cli/commands/dev.py` owns storage migration, SQLite schema inspection, and active
  storage backend diagnostics.
- `cli/commands/pack.py` owns thought-pack export/import/list/inspect behavior,
  including pack path resolution and human-readable archive sizes.
- `cli/commands/eval.py` owns conversation and notification fixture evaluation
  orchestration for the canonical `dev eval` route. Every
  evaluator returns one typed `EvalResult` per scenario; the command derives
  totals and exit status from those results and must not infer fixture counts
  from pytest output, hard-coded constants, or process return codes.
- `cli/commands/system.py` owns one-shot status, health, effective-config, and log
  tail commands. Interactive log views and default/chat session orchestration
  remain in `nuself.cli`.
- Memory CLI commands live together under the `cli/commands/memory/` package and
  are split by subdomain instead of collected in one oversized module.
  `cli/commands/memory/profile.py` owns profile list/search/show/delete/reindex
  handlers and their list ordering and handle resolution.
  `cli/commands/memory/source.py` owns source ingest/list/show/delete/chunks/search/
  extract handlers and source-specific output formatting.
  `cli/commands/memory/candidate.py` owns candidate review handlers, ordering, and
  single/multiple visible-handle resolution. `cli/commands/memory/common.py` owns
  command-layer memory trace recording shared across memory command modules.
  `cli/commands/memory/graph.py` owns symbolic graph nodes/edges/search/path/closure
  handlers and graph-specific text formatting.
  `cli/commands/memory/entries.py` owns durable entry CRUD/search/preview/stats/
  relations/types/reindex/unquarantine handlers. It also exposes parser type
  choices and REPL preview rendering as explicit shared CLI interfaces.
  `cli/commands/memory/maintenance.py` owns explicit curator/optimizer runs and
  durable entry import/export commands.
  `cli/commands/memory/parser.py` owns the complete memory command argument tree;
  the root parser composes it as one subsystem registration.
- Extracted command modules accept `argparse.Namespace` only at the CLI edge;
  domain work continues to flow through lifecycle, client, service, and
  repository APIs.
- Parser command names, exit codes, stdout/stderr placement, and rendered text
  remain governed by `cli.md` and must not change during a mechanical split.
- REPL session orchestration remains separate from one-shot command handlers;
  later extractions should not introduce imports from subsystem command modules
  back into `nuself.cli`.
- REPL modules live under `nuself.cli.repl`; `cli/repl/types.py` owns result contracts,
  and transcript/session/command modules depend on those contracts rather than
  importing the CLI composition root.
- `cli/repl/transcript.py` owns transcript projection, Markdown normalization,
  persistence naming, shareable-log filtering, clipboard integration, export
  command parsing, explicit save coordination, and connection-exit autosave.
  It consumes session behavior through a structural protocol and never imports
  `cli/repl/session.py`.
- `cli/repl/session.py` owns per-connection message/log capture and export
  progress state.
- `cli/repl/commands.py` owns subsystem REPL commands and their focused help
  text.
- `cli/repl/dispatcher.py` owns top-level registry matching, subsystem routing,
  interactive thread lifecycle commands, dev status/logs, export routing, and
  unknown-command help. It depends on REPL command/session APIs and never
  imports the CLI composition root; the root only wires it as a callback.
- `cli/repl/input.py` owns prompt-toolkit input, deduplicated history,
  completion, and top-level interactive help. Completion control flow invokes
  Chat- or Reason-owned audit adapters and does not construct subsystem audit
  presentation.
- `cli/repl/activity.py` owns incremental activity reads, transcript capture
  inclusion, user-visible event filtering, failure classification, and
  rendering. It also owns the bound send thread and daemon activity
  subscription lifecycle, including log-poll fallback, final drain, and
  best-effort close. The composition root supplies polling configuration and
  injected reader/presenter effects but does not implement thread or transport
  control flow.
- `cli/repl/turns.py` owns one logical interactive chat turn: stable turn id,
  bounded transport retry, exact runtime context, live activity coordination,
  session message/log association, memory/reply presentation order, and error
  deduplication. Configured retry/poll values and rendering effects are
  injected by the composition root.
- `cli/repl/runtime.py` owns the interactive session loop and receives
  application effects through `ReplCallbacks`. Transcript auto-save and memory
  curation execute once each through named cleanup aggregation that preserves
  any main-loop primary failure.
- `runtime/cleanup.py` owns domain-neutral ordered cleanup execution,
  `CleanupFailure`, and canonical `{step,error}` audit records. Lifecycle
  owners retain step composition, diagnostics, primary-error policy, and
  domain error types.

Conversation runtime code lives under `agent/chat/`. `types.py` owns settings,
structured response/result records, typed turn state, and graph error contracts;
`thread.py` owns persistence; `context.py`, `state.py`, `persona.py`,
`response.py`, and `tool_runtime.py` own focused collaborators; and
`runtime.py` wires the LangGraph. The package root is the stable public import
boundary and re-exports caller-facing names.

## Memory Architecture Direction

- Prefer open typed memory (`MemoryObject + MemoryTypeDescriptor`) over closed enums.
- Descriptors own validation, summarization, merge, decay, conflict, retrieval, and reflection rules.
- Symbolic memory evolves as a derived open graph with `RelationDescriptor` rules.
- File-backed private memory is authoritative; all indexes are derived and rebuildable.

## Private Memory

- Real personal memory lives in the root `private/` directory.
- `private/` is ignored by Git and must not be committed.
- Code loads from `private/` by default; tests and demos use `examples/private/`.
