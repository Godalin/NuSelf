# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Begin a minimal persona subgraph skeleton while preserving the current LangGraph conversation runtime and file-backed memory boundaries.

The LangGraph runtime migration slice is complete: the conversation graph has isolated driver failure handling, internal node traces, explicit no-tool/tool-call routes, structured supported/unsupported tool request state, and cleaned user-facing docs. The next useful step is a narrow persona subgraph skeleton that proves persona routing can exist without changing memory storage, CLI payloads, or daemon protocol.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- `ConversationGraphDriver` is the only module that imports LangGraph and wraps graph failures as `ConversationGraphRuntimeError`.
- Runtime results carry internal node traces without changing CLI or daemon response payloads.
- Tool calls route through `detect_tool_request`, optional `execute_tool`, and `finalize_response`.
- Tool request state records name, args, support status, and diagnostics.
- File-backed private memory remains authoritative; derived indexes and future runtime mirrors must stay rebuildable.

## Next Steps

1. Define minimal persona node/state types for a single bounded persona, without changing user-facing responses.
2. Add a graph subgraph or driver boundary that can run the persona node internally.
3. Preserve current response metadata, memory context packing, persistence, tool calls, diagnostics, fallback behavior, CLI payloads, and daemon payloads.
4. Add focused tests proving the persona skeleton is internal and does not alter existing chat behavior.

## Not Now

- Full multi-persona orchestration.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.

## Completion Criteria

- A minimal persona node or subgraph boundary exists and is tested.
- Existing chat entrypoints keep their current user-visible behavior.
- Persona internals do not leak into CLI or daemon payloads.
- README TODOs track completed progress, while this file stays limited to the active goal.
