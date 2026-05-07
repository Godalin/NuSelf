# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Continue the LangGraph conversation runtime migration while preserving the current file-backed memory and retrieval boundaries.

The current memory foundation is ready enough for this work: typed memory descriptors, descriptor-backed relations, symbolic graph traversal, and transitive retrieval expansion are implemented. The conversation turn now has a minimal runtime boundary. The next useful step is to make the runtime state and node contracts explicit enough to swap in a real LangGraph implementation later.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` now owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- The runtime still supports structured responses, evidence metadata, unsupported-claim handling, context compression, and explicit memory search tool calls.
- File-backed private memory remains authoritative; derived indexes and future runtime mirrors must stay rebuildable.

## Next Steps

1. Introduce an explicit typed runtime state object for one conversation turn.
2. Split turn execution into clearer node result contracts for context packing, initial LLM response, tool resolution, final response, and compression.
3. Preserve current response metadata, memory context packing, persistence, and deterministic fallback behavior.
4. Add focused tests for the new state/node contracts before adding a LangGraph dependency.

## Not Now

- Full persona subgraphs.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.

## Completion Criteria

- Runtime state and node boundaries are explicit enough to map to LangGraph nodes.
- Existing chat entrypoints keep their current user-visible behavior.
- Tests cover response metadata, persistence, memory context use, tool calls, and fallback behavior through the runtime boundary.
- README TODOs track completed progress, while this file stays limited to the active goal.
