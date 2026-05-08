# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Wire the minimal persona skeleton into the conversation runtime internally while preserving the current user-facing behavior and file-backed memory boundaries.

The minimal persona graph skeleton exists as an internal LangGraph-backed boundary with structured persona contributions and trace output. The next useful step is to call it from the conversation runtime in a strictly internal way, proving persona work can run without changing the final chat answer, CLI payloads, daemon protocol, or durable memory schema.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- `ChatAgent` owns thread persistence while `ConversationGraphRuntime` owns turn execution.
- `ConversationGraphDriver` is the only module that imports LangGraph and wraps graph failures as `ConversationGraphRuntimeError`.
- Runtime results carry internal node traces without changing CLI or daemon response payloads.
- Tool calls route through `detect_tool_request`, optional `execute_tool`, and `finalize_response`.
- Tool request state records name, args, support status, and diagnostics.
- `PersonaGraphDriver` can run a single internal `analyst_self` persona and return structured contributions.
- File-backed private memory remains authoritative; derived indexes and future runtime mirrors must stay rebuildable.

## Next Steps

1. Add an internal persona step to the conversation runtime state or graph.
2. Keep persona contributions internal; do not include them in `ChatResult.to_payload`, CLI output, or daemon payloads.
3. Preserve current response metadata, memory context packing, persistence, tool calls, diagnostics, and fallback behavior.
4. Add focused tests proving persona execution does not alter existing chat behavior.

## Not Now

- Full multi-persona orchestration.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.

## Completion Criteria

- The conversation runtime can execute the minimal persona skeleton internally.
- Existing chat entrypoints keep their current user-visible behavior.
- Persona internals do not leak into CLI or daemon payloads.
- README TODOs track completed progress, while this file stays limited to the active goal.
