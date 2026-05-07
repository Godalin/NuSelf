# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Begin the LangGraph conversation runtime migration while preserving the current file-backed memory and retrieval boundaries.

The current memory foundation is ready enough for this slice: typed memory descriptors, descriptor-backed relations, symbolic graph traversal, and transitive retrieval expansion are implemented. The next useful step is to wrap the existing chat behavior in a small graph-oriented runtime boundary before adding more memory features.

## Immediate Context

- `MemoryQueryService` remains the stable retrieval boundary for memory entries, profile items, source chunks, and graph-derived expansion.
- The temporary chat agent already supports structured responses, evidence metadata, unsupported-claim handling, and explicit memory search tool calls.
- File-backed private memory remains authoritative; derived indexes and future runtime mirrors must stay rebuildable.

## Next Steps

1. Define a minimal conversation orchestrator boundary around the current chat behavior.
2. Add a LangGraph-ready graph skeleton without leaking LangGraph internals into the CLI or daemon protocol.
3. Preserve current response metadata, memory context packing, persistence, and deterministic fallback behavior.
4. Add focused tests for the new runtime boundary before moving more tool execution into graph nodes.

## Not Now

- Full persona subgraphs.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.

## Completion Criteria

- A minimal conversation graph runtime boundary exists.
- Existing chat entrypoints keep their current user-visible behavior.
- Tests cover response metadata, persistence, memory context use, and fallback behavior through the new boundary.
- README TODOs track completed progress, while this file stays limited to the active goal.
