# Changelog

All notable user-visible changes to NuSelf are tracked here.

This project follows the versioning rules in [`docs/spec/versioning.md`](docs/spec/versioning.md).

## Unreleased

### Added

- Added `nuself daemon health`, backed by a typed daemon health request, to
  inspect background worker liveness, consecutive failures, last success, and
  last error.

### Changed

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
