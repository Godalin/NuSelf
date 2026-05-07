# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Add graph runtime observability while preserving the current file-backed memory and retrieval boundaries.

The LangGraph conversation graph now executes one chat turn through an isolated driver, and graph failures preserve persisted thread state. The next useful step is to expose lightweight runtime diagnostics so graph turns can be debugged before adding persona subgraphs or richer agent routing.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` now owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- `ConversationGraphDriver` is the only module that imports LangGraph and wraps graph failures as `ConversationGraphRuntimeError`.
- Failed graph turns do not corrupt persisted thread state.
- File-backed private memory remains authoritative; derived indexes and future runtime mirrors must stay rebuildable.

## Next Steps

1. Add lightweight node execution tracing inside the conversation runtime state or result.
2. Keep traces internal first; do not change CLI or daemon response payloads unless a clear consumer exists.
3. Preserve current response metadata, memory context packing, persistence, tool calls, and deterministic fallback behavior.
4. Add focused tests for successful node traces and graph-driver failure traces.

## Not Now

- Full persona subgraphs.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.

## Completion Criteria

- Runtime node traces are available for successful and failed graph turns.
- Existing chat entrypoints keep their current user-visible behavior.
- Tests cover node trace ordering without changing CLI or daemon payloads.
- README TODOs track completed progress, while this file stays limited to the active goal.
