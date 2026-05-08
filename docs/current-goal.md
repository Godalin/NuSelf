# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Surface compact persona activity summaries in the REPL while keeping persona internals out of user-facing payloads.

The minimal persona graph skeleton now runs behind an activation gate inside the conversation runtime on explicit requests or discussion-depth cues. The next useful step is to render that internal persona activity as compact `[selves]` summaries in the REPL or logs, while keeping `ChatResult.to_payload`, CLI payloads, daemon payloads, and durable memory schema unchanged.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- `ConversationGraphDriver` is the only conversation module that imports LangGraph and wraps graph failures.
- `PersonaGraphDriver` can run a single internal `analyst_self` persona and return structured contributions.
- Interactive chat already has compact activity events, so persona activity summaries can fit the same REPL channel without changing answer payloads.
- Persona work must not run on every trivial turn by default.
- Persona internals must not leak into `ChatResult.to_payload`, CLI payloads, daemon payloads, or durable memory schema.

## Next Steps

Render compact persona activity summaries for activated turns in the REPL/log path, keep trivial turns silent, and preserve the current response metadata, memory packing, persistence, tool calls, diagnostics, and fallback behavior as-is.

## Not Now

- Full multi-persona orchestration.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- Activated turns can surface compact persona activity summaries without changing user-facing payloads.
- Trivial chat turns still skip persona work by default.
- Existing chat entrypoints keep current user-visible behavior.
- Persona internals do not leak into CLI or daemon payloads.
- README TODOs track completed progress, while this file stays limited to the active goal.
