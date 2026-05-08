# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Wire the minimal persona skeleton into the conversation runtime behind an activation gate.

The minimal persona graph skeleton exists as an internal LangGraph-backed boundary with structured persona contributions and trace output. The next useful step is to call it from the conversation runtime only when an explicit request or discussion-depth heuristic activates persona work. Persona contributions should stay internal and may surface in the REPL only as compact activity summaries later.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- `ConversationGraphDriver` is the only conversation module that imports LangGraph and wraps graph failures.
- `PersonaGraphDriver` can run a single internal `analyst_self` persona and return structured contributions.
- Interactive chat now has compact activity events, so future persona discussion should eventually appear as `[selves]` summaries rather than final-answer text.
- Persona work must not run on every trivial turn by default.
- Persona internals must not leak into `ChatResult.to_payload`, CLI payloads, daemon payloads, or durable memory schema.

## Next Steps

1. Add a small persona activation policy for explicit user requests and high-depth discussion cues.
2. Add an internal persona step to the conversation runtime state or graph, gated by that policy.
3. Keep persona contributions internal; do not include them in `ChatResult.to_payload`, CLI output, or daemon payloads.
4. Preserve response metadata, memory context packing, persistence, tool calls, diagnostics, and fallback behavior.
5. Add focused tests proving trivial chat skips persona work and activated turns can execute the minimal persona skeleton without changing user-visible payloads.

## Not Now

- Full multi-persona orchestration.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- Conversation runtime can execute the minimal persona skeleton internally when activated.
- Trivial chat turns skip persona work by default.
- Existing chat entrypoints keep current user-visible behavior.
- Persona internals do not leak into CLI or daemon payloads.
- README TODOs track completed progress, while this file stays limited to the active goal.
