# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Move tool handling toward graph-native routing while preserving the current file-backed memory and retrieval boundaries.

The LangGraph conversation graph now has isolated driver failure handling and internal node traces. The next useful step is to make the existing `search_memory` tool path more graph-native, so tool execution can become a distinct route before adding persona subgraphs or richer agent routing.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` now owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- `ConversationGraphDriver` is the only module that imports LangGraph and wraps graph failures as `ConversationGraphRuntimeError`.
- Runtime results carry internal node traces without changing CLI or daemon response payloads.
- File-backed private memory remains authoritative; derived indexes and future runtime mirrors must stay rebuildable.

## Next Steps

1. Split tool request detection from tool execution in the runtime state.
2. Add a graph route that skips tool execution when the initial response has no supported tool call.
3. Preserve current response metadata, memory context packing, persistence, tool calls, diagnostics, and deterministic fallback behavior.
4. Add focused tests for no-tool and tool-call graph routes.

## Not Now

- Full persona subgraphs.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.

## Completion Criteria

- Tool and no-tool paths are explicit graph routes.
- Existing chat entrypoints keep their current user-visible behavior.
- Tests cover both routes without changing CLI or daemon payloads.
- README TODOs track completed progress, while this file stays limited to the active goal.
