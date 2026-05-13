# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](docs/TODOs.md), not here.

## Focus

Extend the chat agent from a pure Q&A interface into a **conversational decision proxy** that can perform user-facing actions during chat: inspect pending reflections, manage memory state, and surface proactive ideas naturally.

## Immediate Context

The chat agent tool suite is now complete:

- **Memory curation**: `archive_memory`, `update_memory_importance`
- **Reflection consumption**: `list_pending_reflections`, `dismiss_reflection`
- **Memory search**: `search_memory`
- **Behavioral guidelines**: Agent proactively introduces reflection ideas when conversation rhythm allows; dismisses on disinterest; archives/adjusts importance on user signal.

The persona discussion system generates genuinely distinct voices via LLM-backed nodes, with all turn participants running in a single shared graph invocation.

## Next Steps

1. **Dismiss → clear lifecycle**: Consider whether dismissed reflections should auto-clear from the outbox after a period, or if `notify clear` is sufficient.
2. **QA integration**: End-to-end test that exercises the full chat → tool invocation → outbox/memory mutation → daemon delivery path.

### Recently Done

- Lowered reflection thresholds and deepened persona discussion parameters.
- Added `ReflectionDiscussionConfig` to the configuration system.
- Specified chat-agent-tools architecture in `docs/spec/chat-agent-tools.md`.
- Implemented `ListPendingReflectionsTool` and `DismissReflectionTool`.
- Wired reflection tools into chat agent runtime and system prompt.
- Replaced deterministic persona placeholder nodes with LLM-backed nodes for distinct discussion voices.
- Fixed multi-persona graph invocation: all turn participants now run in a single shared graph run.
- Added memory management tools (`archive_memory`, `update_memory_importance`) with `archived` review state support.
- Added proactive topic injection behavioral guidelines to system prompt.

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
- All new tools and nodes have unit and integration tests.
- Spec and current-goal are synchronized with implementation.
