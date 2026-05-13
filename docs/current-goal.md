# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](docs/TODOs.md), not here.

## Focus

Extend the chat agent from a pure Q&A interface into a **conversational decision proxy** that can perform user-facing actions during chat: inspect pending reflections, manage memory state, and surface proactive ideas naturally.

## Immediate Context

The chat agent tool suite and lifecycle management are now complete:

- **Memory curation**: `archive_memory`, `update_memory_importance`
- **Reflection consumption**: `list_pending_reflections`, `dismiss_reflection`
- **Memory search**: `search_memory`
- **Behavioral guidelines**: Agent proactively introduces reflection ideas; dismisses on disinterest; archives/adjusts importance on user signal.
- **Dismissed lifecycle**: Old dismissed outbox entries are auto-cleared after 7 days by the delivery loop.

The persona discussion system generates genuinely distinct voices via LLM-backed nodes, with all turn participants running in a single shared graph invocation.

## Next Steps

1. **QA integration**: End-to-end test that exercises the full chat → tool invocation → outbox/memory mutation → daemon delivery path.
2. **README sync**: Update both English and Chinese READMEs to document the new chat agent capabilities.

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
- Auto-clear dismissed outbox entries older than 7 days via `NotificationDeliveryLoop`.

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
- Spec and current-goal are synchronized with implementation.
