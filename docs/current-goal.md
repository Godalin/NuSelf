# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Improve proactive reflection quality and memory curation UX. Recent work completed the LLM-powered idea generation, auto-accept pipeline, YAML-based configuration, and beautified TUI output. Next: evaluate reflection quality, tune thresholds, and add vector/hybrid indexes.

## Immediate Context

- `IdeaCandidateGenerator` uses LLM to scan threads, memory, and sources with structured JSON output.
- `RelevanceGate` uses `config.relevance_threshold` from `private/reflection_config.yaml`.
- `MemoryCurator` auto-accepts candidates into durable entries by default (`auto_accept=True`).
- Competitive persona discussion persists traces to reflection log, viewable via `nuself reflection list/show`.
- All user-facing memory output uses card-style TUI renderers.
- `ReflectionConfig` YAML system covers scheduler, gate, and moderator parameters.
- 545+ tests pass, pyright clean.

## Next Steps

1. Evaluate proactive reflection quality with real usage data; tune thresholds and prompts.
2. Add derived vector and hybrid indexes for semantic memory retrieval.
3. Improve memory search with embedding-based relevance alongside lexical matching.
4. Add `nuself reflection evaluate` command to score reflection quality against outcomes.

## Not Now

- Global unified config system (reflection config is sufficient for now).
- Hot reload or live update of config.
- Config UI or interactive editor.
- LangMem integration (Phase 4).
- Graphiti temporal graph store (Phase 3).

## Completion Criteria

- Reflection quality metrics tracked and thresholds tuned based on real data.
- Vector index prototype integrated with `MemoryQueryService`.
- All new code passes `uv run pytest` and `uvx pyright`.
