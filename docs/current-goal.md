# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Harden the graph-native tool extension boundary while preserving the current file-backed memory and retrieval boundaries.

The conversation graph now has explicit no-tool and tool-call routes for the existing `search_memory` tool path. The next useful step is to make the tool boundary easier to extend before adding persona subgraphs or richer agent routing.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` now owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- `ConversationGraphDriver` is the only module that imports LangGraph and wraps graph failures as `ConversationGraphRuntimeError`.
- Runtime results carry internal node traces without changing CLI or daemon response payloads.
- Tool calls now route through `detect_tool_request`, optional `execute_tool`, and `finalize_response`.
- File-backed private memory remains authoritative; derived indexes and future runtime mirrors must stay rebuildable.

## Next Steps

1. Make supported tool detection return structured tool-call state instead of a boolean only.
2. Keep unsupported tool requests on the no-tool/final-response path with clear diagnostics.
3. Preserve current response metadata, memory context packing, persistence, tool calls, diagnostics, and deterministic fallback behavior.
4. Add focused tests for supported and unsupported tool-call requests.

## Not Now

- Full persona subgraphs.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.

## Completion Criteria

- Supported and unsupported tool requests have explicit, tested graph behavior.
- Existing chat entrypoints keep their current user-visible behavior.
- Tests cover the tool extension boundary without changing CLI or daemon payloads.
- README TODOs track completed progress, while this file stays limited to the active goal.
