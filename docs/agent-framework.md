# Agent Framework Plan

NuSelf should use the LangChain ecosystem as its default agent stack. The core product is a personal, long-lived, memory-grounded agent that can both converse on demand and proactively surface new ideas. That shape needs durable state, thread recovery, long-term memory, explicit human review, and controlled side effects more than it needs a heavyweight "team of agents" abstraction.

## Recommendation

- Use LangGraph as the primary agent runtime.
- Use LangChain for model, tool, prompt, and provider abstractions.
- Use NuSelf domain models for private memory, evidence, persona state, notifications, and review workflows.
- Use LangMem-style memory managers/tools for candidate extraction and memory search once NuSelf's own memory schemas stabilize.
- Treat LlamaIndex as an optional retrieval component later, not as the main runtime.
- Defer CrewAI, AutoGen, Temporal, and Inngest unless a concrete milestone needs their specific strengths.

## Why LangGraph Fits

LangGraph is the right center of gravity because NuSelf needs:

- Durable execution for long-running or interrupted workflows.
- Thread-scoped short-term memory for resumable conversations.
- Cross-thread long-term memory for personal facts, preferences, examples, and agent instructions.
- Conditional routing between deterministic checks, retrieval, model calls, review gates, and notification actions.
- Human-in-the-loop pauses before committing sensitive memory or sending proactive messages.
- Time-travel and checkpoint history for debugging why the mirror said or initiated something.

NuSelf should use LangGraph checkpointers for graph execution state, not as the core product memory boundary. NuSelf intentionally does not model the person as separate sessions; durable memory should be managed by the memory subsystem described in [docs/memory-management.md](memory-management.md).

## Lightweight Multi-Agent Model

NuSelf should support multiple "thought selves" without adopting a heavy multi-agent framework. Implement them as LangGraph nodes or subgraphs with different prompts, retrieval scopes, and structured output schemas.

Default personas:

- `analyst_self`: decomposes a question into concepts, assumptions, and implications.
- `skeptic_self`: looks for weak claims, contradictions, missing evidence, and overconfidence.
- `builder_self`: turns discussion into plans, artifacts, and next actions.
- `historian_self`: searches private memory for related past thoughts, experiences, and source material.
- `care_self`: evaluates emotional, relational, and life-context consequences.
- `synthesizer`: integrates persona outputs and is the only persona allowed to produce final user-facing text.

The multi-persona loop should be bounded:

- Route only to relevant personas by default.
- Run persona nodes in parallel when possible.
- Allow at most one critique round in normal operation.
- Require structured outputs with claims, evidence references, concerns, questions, and confidence.
- Keep all personal facts grounded in private memory or marked as inference.
- Let the synthesizer decide whether to answer, ask a question, create a memory candidate, or propose a proactive notification.

## Proactive Agent Model

NuSelf should not be only a chatbot. It should have a background agent that periodically reflects on private memory, recent conversations, open questions, and new source material.

Proactive flow:

```text
Schedule or event trigger
  -> gather recent memory, threads, and source changes
  -> generate idea candidates
  -> run lightweight persona discussion
  -> score relevance and interruption cost
  -> write to outbox
  -> notify only when policy allows
```

Candidate types:

- A contradiction or tension between older and newer thoughts.
- A question worth reopening.
- A connection between two previously separate ideas.
- A possible profile update that needs review.
- A concrete next action suggested by recent conversations.
- A shareable memory bundle suggestion.

## Notification And Deep Links

Agent graph nodes must not send notifications directly. They should write notification intents to an outbox. A separate delivery service reads the outbox and sends messages through configured adapters.

Initial adapters:

- macOS notification adapter for local system messages.
- Email adapter for messages that should survive outside the local UI.
- Local web deep link adapter that opens a new or existing thread.

Notification payloads should include:

- Candidate title and short reason.
- Evidence references or source summary.
- Thread routing: create a new thread or continue an existing thread.
- Cooldown and priority metadata.
- Delivery status and error details.

Deep links should route to a persisted LangGraph thread ID or create a new thread with the proactive candidate as initial state.

## Framework Boundaries

Use other frameworks only when they provide a clear component advantage:

- LlamaIndex can help with document parsing, indexing, or retrieval if LangChain retrieval becomes insufficient.
- CrewAI is not the default because NuSelf needs personal-state fidelity more than crew/task conventions.
- AutoGen is not the default because its multi-agent conversation model is heavier than the desired persona subgraph.
- OpenAI Agents SDK is useful as a provider-specific reference, but NuSelf should keep provider boundaries narrow.
- Temporal or Inngest can be revisited if proactive jobs need distributed scheduling, retry guarantees, or production-grade background orchestration.
