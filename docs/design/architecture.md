# NuSelf Architecture

NuSelf is an AI mirror for one person's ideas, memory, experience, and reasoning habits. The system should help people continue a deep conversation when the original person is unavailable, while making clear what is recalled evidence, inferred stance, and newly generated reasoning.

## Product Principles

- Personal fidelity first: answers should preserve the person's concepts, vocabulary, values, and uncertainty.
- Traceable reasoning: when possible, the system should point back to source memories, notes, conversations, or derived profiles.
- Clear epistemic status: separate direct source material, stable profile knowledge, model inference, and speculation.
- Incremental growth: every ingestion, profile update, and evaluation path should be testable as a small component.
- Local-first core: the project should be usable as a standard Python application before adding hosted services.
- Current-design implementation: during early development, update interfaces directly instead of preserving compatibility with obsolete local APIs.

## LLM-Driven Decision Architecture

A defining characteristic of NuSelf is that **the LLM is not only a generator but also the primary decision-maker** for all judgments that require understanding context, nuance, and user state. Hardcoded numeric formulas and keyword heuristics are replaced with LLM-backed contextual decisions wherever the "right answer" depends on "what this means for this person, right now."

### Manifesto: Ten Principles

These ten principles guide every L2 decision in NuSelf. They are non-negotiable project identity.

1. **The LLM is the judge, not a calculator.** When a decision depends on meaning, mood, relevance, or personal context, the LLM decides. Weighted formulas, keyword lists, and length thresholds are mechanical fallbacks, not primary logic.

2. **Prompt is policy.** The behavior of the system at a decision point is defined by the prompt, not by code. Changing a decision policy means editing a prompt, not rewriting arithmetic.

3. **Context is complete.** Every L2 prompt receives the full relevant context: the candidate, recent history, current user state, and time. The LLM is never asked to judge in a vacuum.

4. **Schema over freedom.** LLM outputs are constrained to typed JSON schemas with validated fields. Unstructured reasoning is allowed inside `reason` strings; the decision itself is structured.

5. **Fail safe, fail visible.** If the LLM call fails, the parser breaks, or a required field is missing, the system falls back to the safest deterministic default (typically "reject" or "do nothing") and logs the failure. An L2 failure must never crash the pipeline.

6. **Traceable judgment.** Every L2 decision is logged with its raw prompt, parsed output, and reasoning string. The user should be able to inspect why a reflection was approved or why a persona was activated.

7. **Mechanical separation.** L0 (infrastructure) and L1 (policy) remain deterministic code. The LLM does not count seconds, enforce daily caps, or clamp floats. Human-defined rules stay in code; interpretive judgment moves to the LLM.

8. **Progressive replacement.** Replace heuristics one decision point at a time. Each replacement is a self-contained change: new class, new prompt, new tests. Do not refactor the whole system at once.

9. **Novelty is semantic, not lexical.** String-matching novelty (`body in last_body`) is a mechanical hack. True novelty is judged by meaning: a variant of an old topic can be novel if it brings a new angle.

10. **Human override.** Every L2 decision is a recommendation, not a command. The user can override, dismiss, or archive any LLM-approved reflection. The system never treats LLM judgment as absolute.

### Three-Layer Decision Stack

Every system decision is classified into one of three layers:

| Layer | Name | Responsibility | Implementation |
|---|---|---|---|
| **L0** | Infrastructure | Mechanical, stateless operations | Deterministic code |
| **L1** | Policy | User-configurable system rules | Config-driven deterministic |
| **L2** | Judgment | Context-aware qualitative decisions | **LLM-driven** |

**L0 examples**: file I/O, JSON parsing, clamping values to [0, 1], time arithmetic, string tokenization.

**L1 examples**: `daily_cap`, `quiet_hours`, `cooldown_seconds`, `recent_messages` limit — rules the user explicitly configures and the system enforces mechanically.

**L2 examples**: relevance scoring, novelty assessment, persona matching, discussion depth judgment, emergent persona spawning, and host escalation decisions. These require understanding meaning, user mood, topic relevance, and temporal context.

**Key rule**: If a decision requires interpreting "what this candidate means relative to this person's recent thoughts," it belongs in L2. If it is purely mechanical or explicitly user-configured, it stays in L0/L1.

### Current L2 Targets

1. **RelevanceGate** (P0): Replace the weighted formula `novelty*0.25 + confidence*0.20 + urgency*0.25 - interruption*0.15` and crude string-matching novelty with an LLM that judges semantic relevance against recent reflections.
2. **LLMBackedActivationPolicy** (P1): Replace `PersonaActivationPolicy` + `HostDiscussionPolicy` with a single LLM-driven policy. One structured prompt receives the user message, memory context, and available persona list; the LLM returns `selected_persona_ids`, `trigger`, `should_escalate`, and `escalation_reason`. No keyword markers, no length thresholds.
3. **PersonaDiscussion scoring** (P2): Replace hardcoded persona-specific score adjustments and consensus thresholds with LLM-reported scores and moderator judgment.

### What Stays Deterministic

- **Time gates** (`cooldown_ok`, `quiet_hours`, `daily_cap`): L1 policy. The LLM does not need to count seconds.
- **Context limits** (`max_threads`, `max_messages`, `max_entries`): L0 infrastructure. Budgeting is mechanical.
- **Lexical retrieval weights** (`memory/query.py`): L0 retrieval scoring. Future hybrid search may add an L2 LLM reranking overlay, but the base lexical layer remains deterministic.
- **Clamping and validation** (`max(0.0, min(1.0, x))`): L0 safety bounds.

## System Shape

The initial implementation should be a modular Python application managed by `uv`.

```text
User Interface
  -> CLI
  -> Daemon Client
  -> Conversation Service
    -> Retrieval Layer
    -> Mirror Profile
    -> Response Orchestrator
    -> Persona Subgraphs
    -> Safety and Epistemic Guards
  -> Proactive Agent Service
    -> Reflection Scheduler
    -> Idea Candidate Generator
    -> Relevance Gate
    -> Notification Outbox
  -> Memory Update Pipeline
    -> Source Ingestion
    -> Normalization
    -> Indexing
    -> Profile Distillation
  -> Evaluation Suite
```

The interaction layer is detailed in [docs/design/interaction.md](interaction.md). The product should be CLI-first, with a local daemon for long-lived state, background reflection, thread persistence, memory indexing, and notification dispatch.

## Private Memory Layout

NuSelf separates the public codebase from private personal memory.

```text
private/                     # ignored by Git; real local personal memory
  manifest.toml
  profile.md
  sources/
  shares/
examples/private/            # committed sample memory for tests and demos
  manifest.toml
  profile.md
  sources/
  shares/
```

The application should actively link to the root `private/` directory at runtime. That means the default configuration resolves private memory from the project root, validates its manifest, and exposes it to ingestion, retrieval, profile loading, and export workflows. Tests, examples, and documentation should use `examples/private/` so the repository remains runnable without private data.

Private memory can also be used for sharing. Shareable subsets should be written under `private/shares/` as explicit export bundles, never by exposing the whole private directory by accident.

## Agent Framework

NuSelf uses the LangChain ecosystem by default. LangGraph is the primary runtime for stateful agent workflows, durable execution, thread persistence, long-term memory, human-in-the-loop pauses, and conditional routing. LangChain provides model, tool, prompt, and provider abstractions.

The detailed framework decision is tracked in [docs/design/agent.md](agent.md). The memory subsystem is detailed in [docs/design/memory.md](memory.md).

Framework boundaries:

- Use LangGraph for the core conversation graph, proactive reflection graph, and lightweight multi-persona discussion.
- Use NuSelf's own typed domain models for private memory, evidence, profile state, notification intents, and review workflows.
- Treat LlamaIndex as an optional retrieval/indexing component later.
- Defer CrewAI, AutoGen, Temporal, and Inngest until a concrete milestone needs their specific strengths.

## Core Modules

### Source Ingestion

Ingests raw personal material such as notes, essays, chat exports, bookmarks, timelines, and manually written profile facts.

Responsibilities:

- Load source documents from local files.
- Resolve the default source root from `private/`, with an explicit override for `examples/private/` in tests and demos.
- Preserve source metadata such as title, date, origin, author, and privacy level.
- Split material into stable chunks without losing citation context.
- Reject malformed input with explicit validation errors.

### Knowledge Store

Stores normalized source chunks and derived profile artifacts.

Responsibilities:

- Keep raw source references immutable once imported.
- Maintain searchable indexes for retrieval.
- Store derived facts, preferences, recurring claims, and known uncertainties separately from raw source text.
- Keep committed sample memory and ignored private memory interchangeable at the repository interface boundary.
- Support re-indexing without changing source identity.
- Treat user-visible memory entries as authoritative; vector, lexical, and graph indexes are derived artifacts.
- Support query-driven retrieval instead of loading all memories into every prompt.
- Evolve memory from closed entry-type literals toward open `MemoryObject` envelopes plus registered `MemoryTypeDescriptor` behavior.
- Maintain a symbolic graph layer with open `RelationDescriptor` definitions for support, contradiction, refinement, preference, dependency, and future relations.

Typed memory should be protocol-based, not enum-bound. A memory type owns its schema, validation, merge rule, decay rule, conflict rule, retrieval rule, and reflection rule. A symbolic relation owns its domain/range expectations, symmetry, transitivity, inverse, temporal policy, confidence policy, and inference/retrieval behavior. File-backed memory objects remain authoritative; graph nodes, graph edges, embeddings, and LangGraph Store mirrors are derived artifacts.

### Mirror Profile

Represents the current model of the person's worldview and communication style.

Responsibilities:

- Capture durable beliefs, interests, taste, vocabulary, life context, and reasoning patterns.
- Track confidence and evidence for each profile item.
- Keep contradictions visible instead of collapsing them too early.
- Distinguish current profile state from historical state when timestamps are available.

### Conversation Service

Handles a user conversation with the mirror.

Responsibilities:

- Build a conversation-specific context from user intent, retrieved sources, and profile state.
- Decide whether the answer should be evidence-heavy, exploratory, personal, or cautionary.
- Produce responses that expose uncertainty instead of fabricating personal knowledge.
- Return structured metadata for citations, confidence, and source usage.

### Interaction Layer

Provides the command-line application, daemon lifecycle controls, local IPC, and user-facing memory/thread management.

Responsibilities:

- Start, stop, inspect, and attach to the local daemon.
- Connect CLI chat commands to an existing daemon when available.
- Start a one-shot local runtime for immediate chat when no daemon is running.
- Manage thread creation, resumption, renaming, archival, unarchival, and deletion.
- Expose memory entries as inspectable, editable, deletable records.
- Keep local runtime files, sockets, pids, logs, and private settings under ignored `private/`.

### Response Orchestrator

Coordinates model calls and deterministic checks.

Responsibilities:

- Assemble prompts from typed inputs rather than ad hoc strings spread across the codebase.
- Enforce output schemas for answer text, cited evidence, uncertainty, and follow-up questions.
- Run post-generation checks for unsupported claims and missing citations.
- Keep provider-specific model code behind a narrow adapter boundary.
- Separate thinking from presentation: internal chat/tool/persona stages decide what should be said, and a dedicated presentation stage decides how to express the final answer to the user.
- Treat presentation as an L2 judgment task. The system may detect boundary failures such as protocol leakage, but should ask the model to regenerate rather than mechanically rewriting user-facing text.

### Persona Subgraphs

Implements lightweight multi-agent discussion between thought selves.

Responsibilities:

- Route each question or proactive candidate to only the relevant personas.
- Run bounded persona discussion rounds with structured outputs.
- Keep persona claims grounded in evidence or clearly marked as inference.
- Let a synthesizer integrate persona outputs before any user-facing response.
- Store persona instructions and feedback as procedural memory, not as hard-coded scattered prompts.

Default personas:

- `analyst_self`: decomposes concepts, assumptions, and implications.
- `skeptic_self`: looks for contradictions, missing evidence, and overconfidence.
- `builder_self`: turns ideas into plans, artifacts, and next actions.
- `historian_self`: retrieves related private memory and past conversations.
- `care_self`: evaluates emotional, relational, and life-context consequences.
- `synthesizer`: integrates the discussion and decides the next action.

### Proactive Agent Service

Allows NuSelf to initiate contact when it finds a worthwhile idea, tension, reminder, or question.

Responsibilities:

- Run scheduled or event-triggered reflection over private memory, recent threads, and new sources.
- Generate idea candidates with evidence, confidence, novelty, and suggested thread routing.
- Use persona subgraphs for bounded internal discussion of high-value candidates.
- Apply relevance, cooldown, and interruption-cost gates before notification.
- Write notification intents to an outbox instead of sending directly from agent nodes.
- Link each notification to a new or existing conversation thread.

### Notification Outbox

Separates agent decisions from external side effects.

Responsibilities:

- Persist notification intents, delivery state, retries, and errors.
- Support macOS notification and email adapters as initial delivery mechanisms.
- Include deep links that open a local NuSelf thread or create a new thread from the candidate.
- Prevent duplicate or repeated notifications through idempotency keys and cooldown metadata.

### Memory Update Pipeline

Turns new conversations or new documents into candidate profile updates.

Responsibilities:

- Propose memory/profile changes without silently committing them.
- Record why a profile item was added, changed, or rejected.
- Allow human review before durable personal facts are updated.
- Keep conversation-derived memory lower confidence than direct authored sources unless reviewed.
- Use a dedicated memory curator for extraction, consolidation, contradiction detection, and candidate generation.
- Commit durable memory only through review or explicit policy gates.

### Evaluation Suite

Tests whether the mirror remains faithful, useful, and honest about uncertainty.

Responsibilities:

- Unit-test ingestion, normalization, retrieval, profile merging, and schema validation.
- Maintain golden conversation cases for core topics.
- Score citation quality, unsupported personal claims, style fidelity, and refusal/uncertainty behavior.
- Provide small fixtures that can run locally without external services where possible.

## Current Package Layout

The source tree evolved during active development. The current layout is:

```text
src/nuself/
  __init__.py
  config.py
  private.py
  cli.py
  llm.py
  logs.py
  eval.py
  reflection.py
  daemon/
    client.py
    server.py
    protocol.py
    lifecycle.py
  domain/
    memory.py
    profile.py
    source.py
  agent/
    chat.py
    graph_driver.py
    persona.py
    tools.py
  memory/
    curator.py
    intake.py
    optimizer.py
    query.py
    repository.py
    source_repository.py
  profile/
    repository.py
  notification/
    __init__.py
    deep_link.py
    email.py
    macos.py
  tui/
    memory.py
    render.py
tests/
  fixtures/
    conversations/
    notifications/
```

Differences from the original suggested layout:

- `proactive/` was folded into top-level reflection modules alongside `IdeaCandidateGenerator` and `LLMRelevanceGate`.
- `evals/` is a single top-level `eval.py` with fixture helpers.
- `agent/` holds the LangGraph conversation runtime, persona subgraph, and tool registry.
- `memory/` includes repository, query, curator, optimizer, and source repository.
- `tui/` provides rendering helpers for CLI output.
- `notification/` keeps the outbox, adapters, and deep link parsing in one place.

## Data Model Boundaries

Use typed domain models for all boundaries between modules.

Important entities:

- `MemoryRoot`: configured private or sample memory directory plus manifest metadata.
- `SourceDocument`: original imported material plus metadata.
- `SourceChunk`: indexed excerpt with source location.
- `EvidenceRef`: pointer from an answer or profile item back to source material.
- `ProfileItem`: durable belief, preference, life fact, style trait, or uncertainty.
- `ConversationTurn`: normalized user/assistant exchange.
- `ThreadRecord`: local conversation metadata and LangGraph thread mapping.
- `MirrorResponse`: answer text plus evidence, confidence, and epistemic status.
- `MemoryCandidate`: proposed update created from new material or conversation.
- `MemoryEntry`: reviewed, editable, user-visible memory record.
- `PersonaDefinition`: prompt, role, retrieval scope, and output schema for a thought self.
- `PersonaContribution`: structured persona output with claims, evidence, concerns, questions, and confidence.
- `IdeaCandidate`: proactive idea, contradiction, reminder, or question proposed for user attention.
- `NotificationIntent`: outbox record for email, macOS notification, or local deep link delivery.

## Trust And Safety Boundaries

NuSelf should avoid pretending to be the person in contexts where that would be misleading. The product can speak as a mirror or simulation, but the implementation should preserve metadata that lets interfaces disclose the nature of the response.

Required guardrails:

- Do not invent private facts when no source supports them.
- Mark inferred answers as inference.
- Prefer "I do not have enough evidence" over confident fabrication.
- Keep high-impact advice, medical/legal/financial claims, and interpersonal escalation cautious and source-aware.
- Keep raw private sources and derived summaries separated so future permission controls are possible.
- Never commit real `private/` contents; only curated `private/shares/` bundles should be copied out intentionally.
- Require a relevance gate before proactive notifications are delivered.
- Keep notification side effects outside LangGraph reasoning nodes by using an outbox.
- Keep daemon runtime files and logs under ignored `private/`.

## Initial Technical Choices

- Python package managed by `uv`.
- Static type checking with `uvx pyright`.
- LangGraph as the primary stateful agent runtime.
- LangChain for model, prompt, tool, and provider abstractions.
- Pydantic or dataclasses for typed domain models.
- A local file-backed store for the first version, with repository interfaces that can later support SQLite or vector databases.
- Root `private/` as the default ignored local memory directory.
- Committed `examples/private/` as the public sample memory directory.
- Unix domain socket IPC for the first local daemon protocol.
- Provider adapters for LLM calls, with no provider-specific code in domain modules.
- Tests grouped by sub-component so ingestion, retrieval, profile logic, and orchestration can be validated independently.
