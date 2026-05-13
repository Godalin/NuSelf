# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](docs/TODOs.md), not here.

## Focus

Extend the chat agent from a pure Q&A interface into a **conversational decision proxy** that can perform user-facing actions during chat: inspect pending reflections, manage memory state, and surface proactive ideas naturally.

## Immediate Context

The conversational decision proxy milestone is now feature-complete:

- **5 chat agent tools**: `search_memory`, `list_pending_reflections`, `dismiss_reflection`, `archive_memory`, `update_memory_importance`
- **Behavioral guidelines**: Agent proactively introduces reflection ideas, dismisses on disinterest, archives/adjusts importance on user signal.
- **Dismissed lifecycle**: Auto-cleared after 7 days by the delivery loop.
- **LLM-backed persona discussion**: Distinct voices, single graph invocation per turn.
- **Reflection thresholds lowered**: More ideas enter discussion; discussion depth increased.
- **READMEs synchronized**: Both English and Chinese versions document new capabilities.

## Next Steps

1. **QA integration**: End-to-end test exercising chat → tool invocation → memory/outbox mutation.
2. **Stabilize**: Run extended manual REPL verification to confirm tool invocation and memory curation work smoothly in practice.

### Recently Done

- Lowered reflection thresholds and deepened persona discussion parameters.
- Added `ReflectionDiscussionConfig` to the configuration system.
- Specified chat-agent-tools architecture in `docs/spec/chat-agent-tools.md`.
- Implemented reflection consumption tools (`list_pending_reflections`, `dismiss_reflection`).
- Implemented memory management tools (`archive_memory`, `update_memory_importance`) with `archived` review state.
- Replaced deterministic persona nodes with LLM-backed nodes for distinct discussion voices.
- Fixed multi-persona graph invocation: all participants run in a single shared graph run.
- Added proactive topic injection behavioral guidelines to system prompt.
- Auto-clear dismissed outbox entries older than 7 days.
- Updated README.md and README.zh-CN.md.

## Not Now

- LLM-less reflection (Phase 3).
- Hot reload of reflection config.
- Vector and hybrid indexes.
- Automatic reflection-to-memory conversion without user chat engagement.

## Completion Criteria

- Chat agent can list, dismiss, archive, and re-prioritize memory during conversation.
- Persona discussion traces contain genuinely distinct per-persona utterances.
- Tool results and discussion traces are injected back into context correctly.
- System prompt guides the agent on when to surface vs. dismiss ideas.
- Dismissed reflections do not accumulate indefinitely in the outbox.
- All new tools and nodes have unit and integration tests.
- READMEs and specs are synchronized with implementation.
