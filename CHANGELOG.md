# Changelog

All notable user-visible changes to NuSelf are tracked here.

This project follows the versioning rules in [`docs/spec/versioning.md`](docs/spec/versioning.md).

## Unreleased

### Added

- Reflection creation now records a `kind="reflection"` thought trace, enabling users to trace why a specific reflection was produced.
- Memory curator auto-accept now records a `kind="memory_update"` thought trace linked to the source chat turn trace, so users can trace from a memory entry back to the conversation that produced it.
- Manual CLI operations (`memory add`, `memory import`, `candidate accept`, `candidate merge`) now also record `memory_update` traces for full provenance coverage.

- Added `SqliteStore` — general-purpose sync `BaseStore` implementation backed by SQLite, usable by any agent for persistent JSON document storage.
- Added `ScopedWorkspace` — namespace-scoped wrapper around `SqliteStore` that auto-injects a prefix (e.g. thread ID) so agents don't manage namespaces manually.
- Added `build_workspace_tools()` — factory that produces `workspace_put`/`workspace_get`/`workspace_search`/`workspace_delete` LangChain StructuredTool instances from a `ScopedWorkspace`.
- Added `ReasonService.workspace(thread_id)` — returns a thread-scoped `ScopedWorkspace` backed by the thread's private SQLite database.
- Added subsystem-prefixed chat service tools, including `memory_count`, `reflection_count`, `reason_count`, and `trace_count` for quick service-size queries.
- Added `reason watch` CLI command — continuously polls a reasoning thread for new steps and prints them incrementally.
- Added `TerminalTheme` color support to `render_reason_row`, `render_reason_detail`, and `render_step_watch_entry` — status, step kinds, tags, and timestamps are now colored.
- Added `DaemonReasonSchedulerConfig` with `interval_seconds` to daemon config schema.
- Added background reasoning scheduler — `ReasonAdvancer` (LLM step generation) + `ReasonScheduler` (polling thread) wired into daemon lifecycle.
- Added `skip_next_advance_until` field to `ReasoningThread` for cooldown support in the scheduler.
- Added past-thought context injection to `ReasonAdvancer` — the LLM step generator now queries `MemoryQueryService` and `ReflectionRepository` before each advance and injects relevant memories and recent reflections into the prompt.
- Added `selves_consult`, a chat-callable multi-persona subagent tool for perspective synthesis and competitive discussion.
- Added markdown-fenced JSON support to the fallback `parse_chat_response` parser, accepting ` ```json\n{...}\n``` ` responses for test compatibility.

### Changed

- **Chat graph simplified from 9 to 4 nodes.** Removed `persona_activation`, `initial_response`, `detect_tool_request`, `execute_tool`, and `finalize_response` nodes. The graph is now `prepare_context → respond → state_update → compression`.
- **Chat agent tool invocation is now fully LangChain-native.** Removed the entire NuSelf-owned manual tool protocol: `[Tool call:]` markers, `[TOOL_CALL]` blocks, the `tool`/`tool_args` JSON envelope, and the 4-node tool loop were all deleted. LangChain `create_agent` with `response_format=ChatStructuredOutput` handles the complete model/tool loop internally.
- **`respond_node` replaced `initial_response`.** The single node calls `supervisor.complete()` once, which runs the full LangChain agent (including any tool calls). Retry is still available for boundary-protocol leaks but no longer involves multi-turn tool chaining.
- **`response.py` is the single source** for `DraftResponse`, `PresentedResponse`, `ParsedChatResponse`, `parse_chat_response`, `is_parsed_user_facing_safe`, `apply_unsupported_claim_guard`, and protocol leak detection. `chat.py` imports all response/parsing types from `response.py`, eliminating ~350 lines of duplicate code.
- Removed ~450 lines of manual tool protocol code from `chat.py` (detection regexes, tool-name map, `_parse_chat_response` duplicates, `_detect_tool_call`, `_invoke_tool`, `_complete_after_tool_loop`, `_synthesize_response`).
- Removed the following tests for the deleted manual tool protocol: `test_chat_agent_tool_invocation_with_memory_search`, `test_chat_agent_end_to_end_memory_archive_via_tool`, `test_chat_agent_recovers_raw_tool_marker_without_leaking`, `test_chat_agent_recovers_tool_call_block_and_normalizes_tool_name`, `test_chat_agent_chains_multiple_fallback_tool_calls_and_skips_persona`.

- Reflection creation now records a `kind="reflection"` thought trace, enabling users to trace why a specific reflection was produced.
- Memory curator auto-accept now records a `kind="memory_update"` thought trace linked to the source chat turn trace, so users can trace from a memory entry back to the conversation that produced it.
- Manual CLI operations (`memory add`, `memory import`, `candidate accept`, `candidate merge`) now also record `memory_update` traces for full provenance coverage.

- Added `SqliteStore` — general-purpose sync `BaseStore` implementation backed by SQLite, usable by any agent for persistent JSON document storage.
- Added `ScopedWorkspace` — namespace-scoped wrapper around `SqliteStore` that auto-injects a prefix (e.g. thread ID) so agents don't manage namespaces manually.
- Added `build_workspace_tools()` — factory that produces `workspace_put`/`workspace_get`/`workspace_search`/`workspace_delete` LangChain StructuredTool instances from a `ScopedWorkspace`.
- Added `ReasonService.workspace(thread_id)` — returns a thread-scoped `ScopedWorkspace` backed by the thread's private SQLite database.
- Added subsystem-prefixed chat service tools, including `memory_count`, `reflection_count`, `reason_count`, and `trace_count` for quick service-size queries.
- Added `reason watch` CLI command — continuously polls a reasoning thread for new steps and prints them incrementally.
- Added `TerminalTheme` color support to `render_reason_row`, `render_reason_detail`, and `render_step_watch_entry` — status, step kinds, tags, and timestamps are now colored.
- Added `DaemonReasonSchedulerConfig` with `interval_seconds` to daemon config schema.
- Added background reasoning scheduler — `ReasonAdvancer` (LLM step generation) + `ReasonScheduler` (polling thread) wired into daemon lifecycle.
- Added `skip_next_advance_until` field to `ReasoningThread` for cooldown support in the scheduler.
- Added past-thought context injection to `ReasonAdvancer` — the LLM step generator now queries `MemoryQueryService` and `ReflectionRepository` before each advance and injects relevant memories and recent reflections into the prompt.
- Added `selves_consult`, a chat-callable multi-persona subagent tool for perspective synthesis and competitive discussion.
- Added markdown-fenced JSON support to the fallback `parse_chat_response` parser, accepting ` ```json\n{...}\n``` ` responses for test compatibility.

### Changed

- **Chat graph simplified from 9 to 4 nodes.** Removed `persona_activation`, `initial_response`, `detect_tool_request`, `execute_tool`, and `finalize_response` nodes. The graph is now `prepare_context → respond → state_update → compression`.
- **Chat agent tool invocation is now fully LangChain-native.** Removed the entire NuSelf-owned manual tool protocol: `[Tool call:]` markers, `[TOOL_CALL]` blocks, the `tool`/`tool_args` JSON envelope, and the 4-node tool loop were all deleted. LangChain `create_agent` with `response_format=ChatStructuredOutput` handles the complete model/tool loop internally.
- **`respond_node` replaced `initial_response`.** The single node calls `supervisor.complete()` once, which runs the full LangChain agent (including any tool calls). Retry is still available for boundary-protocol leaks but no longer involves multi-turn tool chaining.
- **`response.py` is the single source** for `DraftResponse`, `PresentedResponse`, `ParsedChatResponse`, `parse_chat_response`, `is_parsed_user_facing_safe`, `apply_unsupported_claim_guard`, and protocol leak detection. `chat.py` imports all response/parsing types from `response.py`, eliminating ~350 lines of duplicate code.
- Removed ~450 lines of manual tool protocol code from `chat.py` (detection regexes, tool-name map, `_parse_chat_response` duplicates, `_detect_tool_call`, `_invoke_tool`, `_complete_after_tool_loop`, `_synthesize_response`).
- Removed the following tests for the deleted manual tool protocol: `test_chat_agent_tool_invocation_with_memory_search`, `test_chat_agent_end_to_end_memory_archive_via_tool`, `test_chat_agent_recovers_raw_tool_marker_without_leaking`, `test_chat_agent_recovers_tool_call_block_and_normalizes_tool_name`, `test_chat_agent_chains_multiple_fallback_tool_calls_and_skips_persona`.
- Chat service tools now use subsystem-prefixed names such as `memory_search`, `reflection_list_pending`, `reason_show`, and `trace_search`; old generic tool names are not retained.
- Agent Skills now use local tool placeholders that are rendered from the active tool registry, so skill instructions stay aligned with generated service tool names.
- Direct service-status questions now skip persona activation; tool calling is handled by LangChain inside the respond node.
- Selves/persona work now participates through the same agent tool loop as other services instead of running as a fixed pre-tool chat stage.
- Chat now uses the chat supervisor's structured output directly as the final reply, keeping a boundary retry but removing the extra presentation-agent model call from the normal path.
- Fallback tool marker detection and conversion permanently removed. The non-LangChain fallback path (`parse_chat_response`) accepts only plain text, JSON envelope, or markdown-fenced JSON.
- Chat lifecycle and retry logs now show turn start, completion, transport retry, and final-response retry events in interactive activity output.
- Interactive chat log streaming now tracks seen log-event identities instead of timestamp-sorted offsets, preventing old or delayed events from being replayed into the current turn output.
- Log events now have top-level runtime ownership fields including `turn_id`, `job_id`, `trace_id`, and `source`, with an inherited `LogContext` for daemon requests, chat turns, and service/tool calls.
- Interactive chat log streaming now scopes live activity to the current `turn_id`, preventing visible background or delayed events from being attributed to the active reply.
- Chat service-tool logs now include active thread and top-level turn ownership so tool calls can be attributed to the correct logical chat turn.
- Chat now reuses duplicate same-name/same-argument tool calls within one turn and treats visible `[Tool call: ...]` markers anywhere in the final answer as boundary leaks.
- Chat final responses now prefer LangChain structured output on native LangChain chat models, keeping prompted JSON parsing as a fallback path.
- Presentation now prefers LangChain structured output on native LangChain chat models before falling back to prompted JSON parsing.
- Persona activation, persona contribution, and persona synthesis now prefer LangChain structured output on native LangChain chat models.
- All LangChain model/tool calls now use direct method calls (`model.invoke()`, `tool.invoke()`, `with_structured_output()`) instead of `getattr`+`cast` patterns.
- Chat response parsing, persona activation parsing, and proactive-persona scoring/selection/judgment parsing now try Pydantic `model_validate_json` before falling back to hand-parsed JSON.
- Reflection relevance scoring, candidate generation, memory curator action parsing, memory intake parsing, and memory optimizer action parsing now try Pydantic `model_validate_json` before falling back to hand-parsed JSON.
- Chat service tool logs keep the double-tag header and now put compact tool arguments and results (truncated at 200 chars) in the indented body for debugging, with the full detail stored in JSON log metadata.
- Removed redundant `presentation_started` log event to reduce per-turn log noise.
- Persona summary log is now skipped when the activation gate selects no personas.
- Chat-triggered persona discussions now stream `persona_discussion_step` logs during discussion instead of waiting to dump the full trace at the end.
- Discussion trace logs now render section and turn headers as square-bracket tags, such as `[discussion]` and `[turn-1]`.
- Interactive chat now filters live activity output to current-turn chat, tool, persona, and failure events, while hiding background reason/reflection/memory/trace service logs from the REPL.
- Tool call log formatting simplified: JSON args/results are now pretty-printed with `indent=2` and highlighted via `rich.json.JSON`. The separate `result` parameter was removed from `render_tool_call` — all content goes through the combined body text with `args:`/`result:`/`error:` section headers.

- **Replaced `readline` with `prompt_toolkit`** for interactive CLI input. Robust Unicode/IME composition handling (fixes Chinese input corruption). Input prompt (`NuSelf>`) and section headers (`NuSelf:`, `Logs:`) are now colorized. History is persisted via `FileHistory` with consecutive-duplicate skipping.
- **Terminal output now uses `prompt_toolkit.print_formatted_text`** for all colored/ANSI output. Prompt_toolkit handles terminal capability detection and ANSI parsing, eliminating the need for manual `_supports_256_color()` / `_component_color()` fallback logic. Falls back to `print()` when stdout is not a TTY (piped/non-interactive output).
- Tab completion updated from readline callbacks to prompt_toolkit's `Completer` API.

### Fixed

- `reason_show` chat agent tool now accepts `"current"` as alias for the most recent active reasoning thread.
- `reason_show` description updated to document the `"current"` feature.

- Fixed raw `[Tool call: ...]` text leaking into NuSelf replies by recovering parseable markers into real tool calls and rejecting tool markers at the presentation boundary.
- Fixed older persisted replies with raw `[Tool call: ...]` markers polluting future chat prompts and causing the agent to invent unavailable tools such as `get_recent_memories`.
- Fixed raw `[TOOL_CALL] ... [/TOOL_CALL]` text leaking into NuSelf replies by recovering it into real tool calls and normalizing legacy tool names before execution and logging.
- Fixed chat service-tool logging so reflection, reason, and trace tool calls consistently render with caller/service tags and appear in default transcript exports.
- Tightened LLM endpoint availability status detection so failover only treats exact HTTP 401, 402, 403, and 429 responses as endpoint availability failures.
- Fixed reason trace recording when callers inject a custom reason repository.

### Docs

- Updated `docs/spec/chat-agent-tools.md` to document the 4-node graph, removed sections on fallback tool markers and manual tool protocol.

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
