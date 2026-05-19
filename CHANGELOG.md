# Changelog

All notable user-visible changes to NuSelf are tracked here.

This project follows the versioning rules in [`docs/spec/versioning.md`](docs/spec/versioning.md).

## Unreleased

### Added

### Changed

- Chat-triggered persona discussions now stream `persona_discussion_step` logs during discussion instead of waiting to dump the full trace at the end.
- Discussion trace logs now render section and turn headers as square-bracket tags, such as `[discussion]` and `[turn-1]`.

### Fixed

- Fixed chat service-tool logging so reflection, reason, and trace tool calls consistently render with caller/service tags and appear in default transcript exports.
- Tightened LLM endpoint availability status detection so failover only treats exact HTTP 401, 402, 403, and 429 responses as endpoint availability failures.
- Fixed reason trace recording when callers inject a custom reason repository.

### Docs

- Added post-0.2 stabilization backlog for review-driven refactors that should wait until after local v0.2 testing.

## 0.2.0 - 2026-05-19

### Added

- Added LLM endpoint failover so NuSelf can switch between configured LLM endpoints when an account/subscription endpoint becomes unavailable, with OpenAI-compatible endpoints as the default and `anthropic: true` for Anthropic endpoints.
- Added the trace foundation with `ThoughtTrace`, `TraceLink`, file-backed trace storage, trace search, CLI `trace list/show/search`, and REPL `:trace` commands.
- Added automatic `chat_turn` trace recording when final chat replies cite evidence references.
- Added REPL `:restart` / `:r` for restarting the daemon and reconnecting without leaving the interactive session.
- Added the long-run reason foundation with file-backed reasoning threads, reasoning steps, `nuself reason ...` commands, and REPL `:reason` commands.
- Added generic private workspaces with per-owner SQLite scratch storage, first used by reason threads.
- Added reflection organization for merging similar pending reflection ideas, including `nuself inbox reflection organize`.
- Added reflection promotion into long-run reason threads with trace provenance.
- Added read-only reason and trace tools for chat, with Agent Skills that tell the agent when to consult them.

### Changed

- Chat prompts now treat agent-facing services as tools plus skills, so memory and reflection tools include explicit usage policy instead of appearing only as optional commands.
- Chat service skills now live in Agent Skills `SKILL.md` files instead of hard-coded prompt strings.
- Service/tool calls now log caller and callee tags, such as `[chat] [memory]`, while preserving the existing key/value log format.
- Chat agent tools now register only through LangChain `StructuredTool` objects, with the old NuSelf chat-tool protocol removed and the same loaded tool list visible in ordinary and persona-synthesized response prompts.
- Reorganized CLI and REPL commands around the v0.2.0 command model, moving sources under `memory source`, proactive items under `inbox`, diagnostics under `dev`, and removing old command-path compatibility aliases.
- Reflection no longer blocks new cycles based on pending reflection count; duplicate pressure is handled by organization instead.
- Competitive persona discussion logs now render as `[selves]` activity, and visible discussion notes follow the configured chat language preference.
- `[selves]` logs now render `status` as indented body text and avoid repeating `escalation_reason` in the header, so long activation text does not stretch the header.
- Persona/self activity output now uses structured logs only, so REPL rendering keeps log headers and body text in the same format as other activity logs.

### Fixed

- Fixed REPL chat retry idempotency so daemon timeouts retry the same logical turn, avoid duplicate persisted user inputs, and reuse already-completed turn results instead of rerunning persona work.
- Clarified LLM endpoint logs so exhausted endpoints are distinguished from actual failover attempts.
- Fixed reason logs to use the configured project root.
- Fixed `:reason` with no arguments to show reason command help instead of listing threads.

### Docs

- Planned v0.2.0 around a breaking command cleanup, long-run reasoning, and traceable thought provenance.
- Finalized the first long-run reasoning spec slice and documented reflection organization behavior.

## 0.1.0 - 2026-05-16

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
