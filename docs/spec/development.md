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
- Early development: prefer direct, clean implementation over compatibility shims.
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
file, atomically replaces the destination, and removes the temporary file on
failure while preserving any prior destination.

`write_json_atomic()` validates and serializes the complete payload as strict
JSON before creating its temporary file. Non-string mapping keys, arbitrary
objects, and non-finite floats fail without touching the destination or
creating a temporary artifact.

Subsystems must not define parallel atomic writer helpers or use a fixed
`.tmp` path. Direct `Path.write_text()` remains appropriate only for an
explicit user-selected artifact whose partial-write behavior is documented, or
inside the shared writer itself.

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

## CLI Module Boundaries

`nuself.cli` is a package whose `__init__.py` remains the composition root and
public entrypoint. Parser, command, and REPL implementations live beside it
under the same package.

- `cli/parser.py` owns top-level parser construction and accepts the small set
  of interactive callbacks through `InteractiveHandlers`; it never imports
  `nuself.cli`.
- `cli/handlers.py` owns typed argparse handler binding, help-only group
  binding, and exit-status validation at the single CLI dispatch boundary.
- `cli/commands/daemon.py` owns daemon lifecycle/health handlers and daemon status
  formatting.
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
  orchestration for both the canonical and compatibility CLI routes. Every
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
  persistence naming, shareable-log filtering, and clipboard integration.
- `cli/repl/session.py` owns per-connection message/log capture and export
  progress state.
- `cli/repl/commands.py` owns subsystem REPL commands and their focused help
  text; the composition root only dispatches parsed interactive input.
- `cli/repl/input.py` owns prompt-toolkit input, deduplicated history,
  completion, and top-level interactive help.
- `cli/repl/runtime.py` owns the interactive session loop and receives
  application effects through `ReplCallbacks`.

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
