# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Close the LangGraph runtime migration slice while preserving the current file-backed memory and retrieval boundaries.

The conversation graph now has isolated driver failure handling, internal node traces, explicit no-tool/tool-call routes, and structured supported/unsupported tool request state. Treat this as a documentation-backed stabilization pass: finish the migration review, confirm the boundaries in tests, then update the roadmap documents so the next focus is explicit rather than implied.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` now owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- `ConversationGraphDriver` is the only module that imports LangGraph and wraps graph failures as `ConversationGraphRuntimeError`.
- Runtime results carry internal node traces without changing CLI or daemon response payloads.
- Tool calls route through `detect_tool_request`, optional `execute_tool`, and `finalize_response`.
- Tool request state records name, args, support status, and diagnostics.
- File-backed private memory remains authoritative; derived indexes and future runtime mirrors must stay rebuildable.

## Next Steps (combined)

Audit and validate the LangGraph migration end-to-end: (a) audit chat, daemon, and CLI paths for leftover references to the old temporary runtime; (b) confirm tests cover metadata, persistence, context packing, tool routes, graph failures, and fallback behavior; (c) if no gaps remain, mark the migration slice complete and sync README TODOs and this file's wording; (d) only after these validations pick the next roadmap slice (for example persona subgraphs). Treat these as a single validation-and-decision step rather than disconnected sub-steps.

## Not Now

- Full persona subgraphs.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.

## Completion Criteria

- The runtime migration slice has no remaining old temporary-runtime behavior to remove.
- Existing chat entrypoints keep their current user-visible behavior.
- Tests cover graph runtime behavior across chat, daemon, CLI, tool, failure, and fallback paths.
- The current goal documents the active slice, the immediate validation steps, and the next roadmap decision.
- README TODOs track completed progress, while this file stays limited to the active goal.
