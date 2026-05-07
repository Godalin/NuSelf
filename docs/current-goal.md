# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Continue the LangGraph conversation runtime migration while preserving the current file-backed memory and retrieval boundaries.

The current memory foundation is ready enough for this work: typed memory descriptors, descriptor-backed relations, symbolic graph traversal, and transitive retrieval expansion are implemented. The conversation runtime now has explicit typed turn state and public node contracts. The next useful step is to connect those nodes through a minimal LangGraph driver without changing the CLI or daemon protocol.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` now owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- `ConversationGraphRuntime` exposes typed node methods for context preparation, initial response, tool resolution, state update, and compression.
- File-backed private memory remains authoritative; derived indexes and future runtime mirrors must stay rebuildable.

## Next Steps

1. Add the minimal LangGraph dependency needed for a local conversation graph.
2. Build a graph driver that wires the existing public node methods in order.
3. Preserve current response metadata, memory context packing, persistence, tool calls, and deterministic fallback behavior.
4. Add focused tests proving the LangGraph-backed driver preserves current chat behavior.

## Not Now

- Full persona subgraphs.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.

## Completion Criteria

- A minimal LangGraph-backed conversation graph executes one chat turn.
- Existing chat entrypoints keep their current user-visible behavior.
- Tests cover response metadata, persistence, memory context use, tool calls, and fallback behavior through the graph driver.
- README TODOs track completed progress, while this file stays limited to the active goal.
