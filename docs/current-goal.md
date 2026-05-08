# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Expand the minimal persona layer beyond a single analyst role while keeping persona internals out of user-facing payloads.

The conversation runtime now runs the persona skeleton behind an activation gate and emits compact `[selves]` activity summaries through structured persona logs in interactive chat. The next useful step is to add at least one additional bounded persona and simple relevance routing, while keeping `ChatResult.to_payload`, CLI payloads, daemon payloads, and durable memory schema unchanged.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- `ConversationGraphDriver` is the only conversation module that imports LangGraph and wraps graph failures.
- `PersonaGraphDriver` can run internal personas and return structured contributions.
- Interactive chat now renders persona activity through the existing activity log channel (`persona` component rendered as `[selves]`).
- Persona work must not run on every trivial turn by default.
- Persona internals must not leak into `ChatResult.to_payload`, CLI payloads, daemon payloads, or durable memory schema.

## Next Steps

Add a bounded `skeptic_self` persona and route between `analyst_self` / `skeptic_self` using deterministic cues from user intent. Keep trivial turns silent, keep synthesizer behavior unchanged (assistant reply stays single-voice), and preserve current response metadata, memory packing, persistence, tool calls, diagnostics, and fallback behavior as-is.

## Not Now

- Full multi-persona orchestration.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- Activated turns can route to at least two bounded personas (`analyst_self` and `skeptic_self`) and surface compact persona activity summaries without changing user-facing payloads.
- Trivial chat turns still skip persona work by default.
- Existing chat entrypoints keep current user-visible behavior.
- Persona internals do not leak into CLI or daemon payloads.
- README TODOs track completed progress, while this file stays limited to the active goal.
