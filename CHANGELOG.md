# Changelog

All notable user-visible changes to NuSelf are tracked here.

This project follows the versioning rules in [`docs/spec/versioning.md`](docs/spec/versioning.md).

## Unreleased

### Added

- Nothing yet.

### Changed

- Nothing yet.

### Fixed

- Nothing yet.

### Docs

- Planned v0.2.0 around a breaking command cleanup, long-run reasoning, and traceable thought provenance.

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
