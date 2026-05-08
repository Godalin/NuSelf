# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Incrementally grow bounded internal personas while keeping persona internals out of user-facing payloads.

The conversation runtime now runs bounded persona work behind an activation gate and emits compact `[selves]` activity summaries through structured persona logs in interactive chat. Deterministic routing covers `analyst_self`, `skeptic_self`, `builder_self`, `historian_self`, and `care_self`; explicit multi-perspective prompts route all relevant active personas. A bounded internal `synthesizer_self` now fuses persona contributions into a compact internal synthesis object. The next useful step is to consume that synthesis in response planning while keeping `ChatResult.to_payload`, CLI payloads, daemon payloads, and durable memory schema unchanged.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- `ConversationGraphDriver` is the only conversation module that imports LangGraph and wraps graph failures.
- `PersonaGraphDriver` runs internal personas and a synthesizer step that produces `PersonaTurnState.synthesis`.
- Interactive chat now renders persona activity through the existing activity log channel (`persona` component rendered as `[selves]`).
- Deterministic persona routing currently supports `analyst_self`, `skeptic_self`, `builder_self`, `historian_self`, and `care_self`.
- Mixed-intent precedence is deterministic: `skeptic_self` (risk) → `builder_self` (planning) → `analyst_self` (depth).
- Explicit multi-perspective routing now selects all relevant active personas from deterministic markers.
- Persona work must not run on every trivial turn by default.
- Persona internals must not leak into `ChatResult.to_payload`, CLI payloads, daemon payloads, or durable memory schema.

## Next Steps

Thread synthesized persona insight into internal response planning (e.g., prompt-side guidance) without exposing persona internals in external payloads. Keep trivial turns silent, keep external assistant reply behavior unchanged (single voice), and preserve current response metadata, memory packing, persistence, tool calls, diagnostics, and fallback behavior as-is.

## Not Now

- Full multi-persona orchestration.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- Activated turns can route to at least five bounded request personas, produce an internal synthesizer fusion, and surface compact persona activity summaries without changing user-facing payloads.
- Trivial chat turns still skip persona work by default.
- Existing chat entrypoints keep current user-visible behavior.
- Persona internals do not leak into CLI or daemon payloads.
- README TODOs track completed progress, while this file stays limited to the active goal.
