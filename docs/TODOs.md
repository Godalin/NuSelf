# Project TODOs

This checklist is the user-facing progress board for the project. It summarizes the detailed plans in [docs/development-plan.md](docs/development-plan.md), [docs/design/architecture.md](docs/design/architecture.md), [docs/design/agent.md](docs/design/agent.md), [docs/design/interaction.md](docs/design/interaction.md), and [docs/design/memory.md](docs/design/memory.md). When features are completed or the plan changes, update this file together with the implementation and planning docs.

Short-term implementation focus lives in [docs/current-goal.md](docs/current-goal.md). Use it as the active development target before pulling work from the broader backlog below.

## v0.2.x Stabilization Line (complete — merged to `main`)

- [x] v0.2.1 approval decorator.
- [x] v0.2.2 trace/reason schema cleanup.
- [x] v0.2.3 storage abstraction (StorageBackend protocol + FileStorageBackend + repo refactor).
- [x] v0.2.4 sqlite backend (nuself.sqlite + migration system; FTS5 remains future work).
- [x] v0.2.5 thought pack infrastructure (export/import/inspect + NuHub prep).
- [x] Merge `dev/v0.2.x` into `main` at v0.2.5 (regression coverage folded into v0.3).

## v0.3 Optimization Line (active on `dev/v0.3.x`)

Code-review-driven. See [docs/current-goal.md](current-goal.md) for per-item detail.

- [x] Redesign the interactive tool-approval prompt (`render_approval_prompt`).
- [x] Batch A — correctness/concurrency fixes (daemon handler, export-timer race, persona failover, osascript timeout, config silent-except).
- [x] Batch B — caching/N+1 (config memoize, symbolic-graph cache, shared tool services, sqlite column/find, misc N+1).
- [x] Review follow-up — safe SQLite v1 migration, real reason transactions, project-scoped backends, resilient observable daemon workers, and direct dependency metadata.
- [x] Batch C — dedup & dead-code (shared CLI handle resolution, memory helpers, persona tool builders, dead event/proposal paths, and real derived reindex projections).

## Post-0.2 Stabilization Backlog

These are review-driven refactors that should not block local v0.2 testing. They are good candidates for v0.2.x if they stay mechanical, or v0.3.0 if they reshape subsystem boundaries.

- [x] Split `src/nuself/cli/` into focused CLI layers:
  - [x] Move one-shot command handlers into `nuself.cli.commands`, grouped by
    subsystem.
  - [x] Move parser construction out of the interactive composition module.
  - [x] Move REPL session control and its render/export helpers into focused
    modules.
- [x] Split `ConversationGraphRuntime` into smaller collaborators for context preparation, persona orchestration, tool execution, response synthesis, and state persistence.
- [x] Move generic timestamp helpers out of the memory domain so memory, trace, reason, logs, and daemon code share a neutral time module.
- [x] Replace repeated REPL command string literals with a central command registry that can drive parsing, help text, and aliases.
- [x] Standardize local import policy for optional/heavy modules and make that policy explicit in the development spec.
- [x] Replace rough eval fixture counts with structured fixture result parsing across all dev eval commands.

## Shared Runtime Infrastructure

- [x] Add a sealed, duplicate-safe handler registry and migrate daemon request
  dispatch.
- [x] Centralize typed CLI handler binding and dispatch while retaining
  argparse for parsing.
- [x] Introduce a versioned runtime envelope and neutral correlation context.
- [x] Make structured logs an envelope sink with stable event IDs, serialized
  writes, and incremental cursors.
- [x] Replace tuple queues and process-global job callbacks with typed internal
  job messages, starting with reason output export.
- [x] Add an explicit in-process event publisher for live activity; logs remain
  audit/read-model storage rather than a command bus.
- [x] Decode daemon request/response dictionaries through typed payload
  contracts at the transport boundary.
- [x] Register core runtime event definitions and require explicit domain
  extensions before publication.
- [ ] Add a bounded structured-log retention and rotation policy.
- [ ] Replace cross-process REPL activity polling with an explicit live event
  transport while retaining log-based diagnostics.

## Current Goal

- [x] Complete REPL-shaped TUI, structured logging, and memory inspect polish.
- [x] Add a persona activation gate for explicit requests and high-depth discussion cues.
- [x] Wire the minimal persona skeleton into the conversation runtime internally.
- [x] Keep persona contributions internal while preserving chat, CLI, and daemon payloads.
- [x] Surface compact persona activity summaries in the REPL for activated turns.
- [x] Add deterministic routing for `analyst_self`, `skeptic_self`, and `builder_self`.
- [x] Add one more bounded persona (`historian_self`) and mixed-intent precedence rules.
- [x] Add `care_self` and tune explicit multi-perspective routing.
- [x] Add internal `synthesizer_self` for persona contribution fusion.
- [x] Use synthesized persona insight in internal response planning.
- [x] Refactor the competitive discussion system into a shared service for chat and reflection.
- [x] Make host-driven escalation the sole gate for chat discussion entry.
- [x] Keep discussion traces visible in REPL and logs for both entry points.

## Project Foundation

- [x] Create a standard `uv` Python project with typed package layout.
- [x] Add `uv run pytest` and `uvx pyright` as baseline validation.
- [x] Add versioning, changelog, and release checklist discipline.
- [x] Keep real personal data under ignored root `private/`.
- [x] Commit safe sample private memory under `examples/private/`.
- [x] Keep English and Chinese README files synchronized for user-visible changes.

## CLI And Daemon

- [x] Add `nuself` CLI entrypoint.
- [x] Add daemon lifecycle commands: `start`, `stop`, `status`, `list`, and `logs`.
- [x] Add Unix socket JSONL daemon protocol.
- [x] Add `chat`, `attach`, and daemon-backed attach flows.
- [x] Make root `nuself` a convenient daemon-backed chat entrypoint.
- [x] Add interactive mode with `:q`, `:memory`, command help, and readline history.
- [x] Add a REPL-shaped terminal interaction layer for status, compact activity events, logs, and clearer chat sessions.
- [x] Add read-only REPL memory inspection commands for entries, candidates, profile items, and sources.
- [x] Add readable terminal renderers for memory list and detail views.
- [x] Add structured local log files and a general `nuself logs` viewer.
- [x] Add named thread creation, branching, renaming, and archival.
- [x] Add deep links that open an existing thread or create a new one.

## Memory System

- [x] Add file-backed memory entries under `private/memory/entries/`.
- [x] Add `memory list`, `show`, `add`, `edit`, `delete`, `search`, `preview`, and `reindex`.
- [x] Add shared default working memory under `private/threads/default.json`.
- [x] Serialize shared working-memory writes with a lock.
- [x] Add context compression for long conversations.
- [x] Add deterministic `MemoryQueryService` for relevant memory retrieval.
- [x] Add background Memory Curator Agent for conversation-derived memory updates.
- [x] Run memory curation after chat turns so conversation is the primary memory source.
- [x] Gate memory curation by discussion depth and durable signal instead of fixed turn count.
- [x] Make curator writes conservative: ignore trivial chat, update duplicates before creating, reject raw transcripts.
- [x] Add manual `memory update`.
- [x] Add low-frequency Memory Optimizer Agent for batch cleanup, merging, and deletion of duplicate long-term memories.
- [x] Add manual `memory optimize`.
- [x] Make manual `memory add` infer type and title through a memory intake agent.
- [x] Add memory candidate review queue: list, show, accept, edit, merge, reject.
- [x] Add real-world temporal fields to entries and candidates.
- [x] Route curator and optimizer proposals through the memory candidate review queue.
- [x] Add source-linked evidence records for memory entries.
- [x] Add open `MemoryObject + MemoryTypeDescriptor` registry for typed memory behavior.
- [x] Add built-in descriptors for preference, belief, episode, and instruction memory.
- [x] Add built-in descriptors for goal and concept memory.
- [x] Add descriptor-aware retrieval heuristics and type/tag filters to memory query tools.
- [x] Add first-pass relation-aware retrieval expansion from existing memory links.
- [x] Add rebuildable relation index derived from existing memory links.
- [x] Add `RelationDescriptor` registry for built-in relation behavior.
- [x] Add rebuildable symbolic graph projection over memory entries and relation edges.
- [x] Add transitive-closure retrieval expansion for transitive symbolic relations.
- [x] Extend `MemoryTypeDescriptor` with merge, conflicts, decay, retrieve, reflect, and description hooks.
- [x] Wire descriptor merge into `MemoryOptimizer` and conflict detection into `MemoryCurator`.
- [x] Add `memory types` CLI command and dynamic `--type` choices.
- [x] Add LangMem prototype adapter behind an optional interface.
- [ ] Add derived vector, hybrid, and graph indexes.
- [x] Add open symbolic graph with `RelationDescriptor` rules for support, contradiction, refinement, and dependency.
- [x] Make retrieval expansion respect per-relation `retrieval_rule` (e.g. include both current and superseded vs. direct neighbors only).
- [x] Add graph traversal commands (multi-hop search) using descriptor metadata.
- [x] Add transitive-closure traversal for `transitive=True` relation descriptors.
- [x] Add path-finding commands between specific memory nodes.
- [x] Wire transitive-closure into `MemoryQueryService` automatic context expansion.
- [x] Fix `MemoryQueryService` scoring order: `score <= 0` exclusion should run after quality bonuses (spec-code gap).
- [x] Move `min_importance` filter to pre-scoring phase in `MemoryQueryService` (spec-code gap).
- [x] Fix unknown-type auto-accept conflict between `MemoryCurator` and `MemoryEntryRepository` (spec-code gap).
- [x] Replace the temporary runtime with a LangGraph conversation graph.
- [x] Add memory stats and richer query commands.
- [x] Add `importance` scalar to memory entries, candidates, objects, and profile items with descriptor-aware retrieval scoring.
- [x] Add `--importance` flag to `memory add`, `memory edit`, and `memory candidate edit` CLI commands.
- [x] Add `--sort-by` option to `memory list`, `memory profile list`, and `memory candidate list` CLI commands.
- [x] Add `--review-state` option to `memory list` and `memory candidate list` CLI commands.
- [x] Make `MemoryIntakeAgent` infer importance from text with per-type defaults.
- [x] Add per-type default importance values (e.g. profile facts 0.9, open questions 0.3).
- [x] Add `--min-importance` filter to `memory search`.
- [x] Add importance stats (`avg_importance`, `max_importance`, `avg_importance_by_type`) to `memory stats`.
- [x] Surface importance in `memory show`, `memory list`, and candidate output.
- [x] Add `quarantined` review state for unknown-type draft entries.
- [x] Add `memory unquarantine` CLI command to recover quarantined entries.
- [x] Add structured `IdeaCandidate` and `RelevanceScore` models for proactive agent.
- [x] Enhance `IdeaCandidateGenerator` to scan threads, memory, and sources.
- [x] Replace `RelevanceGate` with `LLMRelevanceGate`: LLM-driven contextual scoring with semantic novelty judgment, structured JSON output, clamping, and safe fallback on failure.
- [x] Add randomized low-frequency reflection with jitter, daily caps, and event triggers.
- [x] Add competitive persona discussion with LLM-selected personas, LLM-reported scores, moderator judgment, blocking vetoes, and synthesizer arbitration.
- [x] Add `NotificationDeliveryLoop` that decouples outbox writing from adapter dispatch.
- [x] Wire configured email/macOS adapters into daemon `NotificationDeliveryLoop` (spec-code gap: currently only LogOnly adapter runs in daemon).
- [x] Enhance `DeepLink` with `new_thread` action for proactive candidate routing.
- [x] Wire proactive agent pipeline into daemon with separate reflection and delivery threads.
- [x] Fix `reflect()` emitting redundant `cycle_no_candidates` after generation-specific events (spec-code gap).
- [x] Add end-to-end test for daemon background reflection scheduler through outbox creation (spec-code gap).

## Ingestion And Knowledge Store

- [x] Add local source ingestion for Markdown and plain text.
- [x] Add source metadata parsing for title, path, date, tags, origin, and privacy.
- [x] Add chunking that preserves source references.
- [x] Add repositories for source documents and chunks.
- [x] Add deterministic source search over imported document chunks.
- [x] Make `memory reindex` rebuild source-derived chunk artifacts.
- [x] Add repositories for profile items.
- [x] Make `memory reindex` rebuild all derived artifacts from authoritative sources.

## Agent Runtime

- [x] Add temporary memory-aware chat agent with OpenAI-compatible `/chat/completions`.
- [x] Add private `config.yaml` configuration with committed `examples/private/config.yaml`.
- [x] Keep deterministic fallback behavior when no API key is configured.
- [x] Add minimal conversation runtime boundary for the LangGraph migration.
- [x] Add typed conversation runtime state and node contracts.
- [x] Replace the temporary runtime with a LangGraph conversation graph.
- [x] Isolate the LangGraph driver boundary and preserve thread state on graph failures.
- [x] Add graph runtime diagnostics for node execution and failures.
- [x] Split conversation tool handling into graph-native routes.
- [x] Harden the graph-native tool extension boundary.
- [x] Close the LangGraph runtime migration slice.
- [x] Add structured response schema with answer text, evidence references, confidence, and epistemic status.
- [x] Add unsupported-claim guard for personal claims without evidence.
- [x] Add tool-based memory search for the conversation agent.
- [x] Make conversation retrieval relation-aware for existing memory links.

## Lightweight Multi-Agent Selves

- [x] Add LangGraph persona subgraph.
- [x] Add minimal internal persona skeleton without changing chat payloads.
- [x] Wire the minimal persona skeleton into the conversation runtime internally.
- [x] Add persona activation gate for explicit requests and high-depth discussion cues.
- [x] Add bounded personas: analyst, skeptic, builder, historian, care, and synthesizer.
- [x] Route only relevant personas per request.
- [x] Make synthesizer the only user-facing voice.
- [x] Store persona instructions and corrections as procedural memory.

## Proactive Reflection And Notifications

- [x] Add low-frequency daemon reflection scheduler with cooldowns and quiet hours.
- [x] Generate idea candidates from recent threads, memory, and sources.
- [x] Add relevance gate with novelty, confidence, urgency, cooldown, and interruption cost.
- [x] Add notification outbox with idempotency keys and delivery state.
- [x] Add log-only notification adapter.
- [x] Add macOS notification adapter.
- [x] Add email adapter using ignored private configuration.
- [x] Link notifications to a new or existing conversation.
- [x] Add color-coded outbox formatting with status colors.
- [x] Add `notify list --status` filter and `notify stats` command.
- [x] Add REPL `:notify list` and `:notify show <id>` commands.
- [x] Add `notify watch` CLI command and REPL `:watch` for real-time outbox streaming.
- [x] Add reflection config env overrides and effective-config inspection in `nuself config`.
- [x] Unify configuration into single `config.yaml` with env overrides replacing scattered `.env` and `reflection_config.yaml`.
- [x] Keep `reflection list` focused on completed or rejected reflection outcomes by default; use `--include-all` or `nuself logs --component reflection` for raw scheduler events.
- [x] Set the daemon reflection check interval default to 10 minutes and provide a root `private/config.yaml` template.
- [x] Let interactive chat reuse the same competitive discussion strategy as background reflection.
- [x] Make shared-discussion results visible in the REPL and structured logs.

## Long-Run Reasoning

- [x] Draft initial design for durable long-run reasoning threads.
- [x] Draft TODO spec for long-run reasoning contracts.
- [x] Implement file-backed reasoning thread and step repositories.
- [x] Add manual `reason` CLI and REPL commands.
- [x] Add manual reasoning advance.
- [x] Add chat tools for user-approved reasoning thread access.
- [x] Add reflection promotion into reasoning threads.
- [x] Add scheduled advance.
- [ ] Add reason notification policy.

## Thought Trace

- [x] Choose `trace` as the user-facing name for thought provenance.
- [x] Draft initial trace design.
- [x] Draft TODO trace spec.
- [x] Add `ThoughtTrace`, `TraceLink`, repository, and renderer.
- [x] Add `nuself trace list/show/search` and `:trace`.
- [x] Record traces for reason thread creation and advance.
- [x] Record traces for reflection promotion into reason.

## Evaluation And Quality

- [x] Add golden conversation fixtures.
- [x] Add local evaluation command.
- [x] Score citation coverage, unsupported personal claims, uncertainty behavior, and style fidelity.
- [x] Add proactive-notification evaluation cases.
