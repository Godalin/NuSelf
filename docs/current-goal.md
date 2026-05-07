# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Stabilize the LangGraph conversation runtime while preserving the current file-backed memory and retrieval boundaries.

The minimal LangGraph conversation graph now executes one chat turn through the existing typed runtime nodes. The next useful step is to harden that integration before expanding into persona subgraphs or richer agent routing.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` now owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- `ConversationGraphDriver` wires context preparation, initial response, tool resolution, state update, and compression through LangGraph.
- File-backed private memory remains authoritative; derived indexes and future runtime mirrors must stay rebuildable.

## Next Steps

1. Isolate the third-party LangGraph boundary so untyped graph builder calls stay out of core chat logic.
2. Add node-level failure handling that returns clear runtime errors without corrupting persisted thread state.
3. Preserve current response metadata, memory context packing, persistence, tool calls, and deterministic fallback behavior.
4. Add focused tests for graph-driver failures and thread-state preservation.

## Not Now

- Full persona subgraphs.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.

## Completion Criteria

- The LangGraph boundary is isolated from core chat logic.
- Existing chat entrypoints keep their current user-visible behavior.
- Tests cover graph-driver failures and thread-state preservation.
- README TODOs track completed progress, while this file stays limited to the active goal.
