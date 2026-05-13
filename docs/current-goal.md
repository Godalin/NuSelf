# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in [`docs/TODOs.md`](docs/TODOs.md), not here.

## Focus

Extend the chat agent from a pure Q&A interface into a **conversational decision proxy** that can perform user-facing actions during chat: inspect pending reflections, manage memory state, and surface proactive ideas naturally.

## Immediate Context

The persona discussion system now generates genuinely distinct voices:

- **LLMBackedPersonaNode**: Each persona responds from its unique perspective using the configured LLM, building on or challenging prior contributions within the same turn.
- **LLMBackedSynthesizerNode**: Produces a crisp per-turn summary rather than concatenating identical notes.
- Both nodes fall back to Minimal placeholders when no LLM is configured.

The reflection consumption tool suite is also live:

- **`list_pending_reflections`**: Agent can view pending outbox ideas during conversation.
- **`dismiss_reflection`**: Agent can mark declined ideas as dismissed.
- Both tools are wired into `ConversationGraphRuntime`, described in the system prompt, and covered by tests.

## Next Steps

1. **Memory management tools**: Add `archive_memory` and `update_memory_importance` tools so the agent can help the user curate memory during conversation.
2. **Proactive topic injection**: Update the system prompt behavioral guidelines so the agent naturally introduces pending reflection ideas when the conversation rhythm allows, rather than only on explicit request.
3. **Dismiss → clear lifecycle**: Consider whether dismissed reflections should auto-clear from the outbox after a period, or if `notify clear` is sufficient.

### Recently Done

- Lowered reflection thresholds and deepened persona discussion parameters.
- Added `ReflectionDiscussionConfig` to the configuration system.
- Specified chat-agent-tools architecture in `docs/spec/chat-agent-tools.md`.
- Implemented `ListPendingReflectionsTool` and `DismissReflectionTool`.
- Wired reflection tools into chat agent runtime and system prompt.
- Replaced deterministic persona placeholder nodes with LLM-backed nodes for distinct discussion voices.

## Not Now

- LLM-less reflection (Phase 3).
- Hot reload of reflection config.
- Vector and hybrid indexes.
- Automatic reflection-to-memory conversion without user chat engagement.

## Completion Criteria

- Chat agent can list and dismiss pending reflections via tool invocation.
- Persona discussion traces contain genuinely distinct per-persona utterances.
- Tool results and discussion traces are injected back into context correctly.
- System prompt guides the agent on when to surface vs. dismiss ideas.
- All new tools and nodes have unit and integration tests.
- Spec and current-goal are synchronized with implementation.
