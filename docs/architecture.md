# NuSelf Architecture

NuSelf is an AI mirror for one person's ideas, memory, experience, and reasoning habits. The system should help people continue a deep conversation when the original person is unavailable, while making clear what is recalled evidence, inferred stance, and newly generated reasoning.

## Product Principles

- Personal fidelity first: answers should preserve the person's concepts, vocabulary, values, and uncertainty.
- Traceable reasoning: when possible, the system should point back to source memories, notes, conversations, or derived profiles.
- Clear epistemic status: separate direct source material, stable profile knowledge, model inference, and speculation.
- Incremental growth: every ingestion, profile update, and evaluation path should be testable as a small component.
- Local-first core: the project should be usable as a standard Python application before adding hosted services.
- Current-design implementation: during early development, update interfaces directly instead of preserving compatibility with obsolete local APIs.

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

The interaction layer is detailed in [docs/interaction-layer.md](interaction-layer.md). The product should be CLI-first, with a local daemon for long-lived state, background reflection, thread persistence, memory indexing, and notification dispatch.

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

The detailed framework decision is tracked in [docs/agent-framework.md](agent-framework.md). The memory subsystem is detailed in [docs/memory-management.md](memory-management.md).

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
- Manage thread creation, resumption, renaming, and archival.
- Expose memory entries as inspectable, editable, deletable records.
- Keep local runtime files, sockets, pids, logs, and private settings under ignored `private/`.

### Response Orchestrator

Coordinates model calls and deterministic checks.

Responsibilities:

- Assemble prompts from typed inputs rather than ad hoc strings spread across the codebase.
- Enforce output schemas for answer text, cited evidence, uncertainty, and follow-up questions.
- Run post-generation checks for unsupported claims and missing citations.
- Keep provider-specific model code behind a narrow adapter boundary.

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

## Suggested Package Layout

```text
src/nuself/
  __init__.py
  config.py
  private.py
  cli.py
  daemon/
    client.py
    server.py
    protocol.py
    lifecycle.py
  domain/
    sources.py
    profile.py
    conversation.py
    evidence.py
  ingestion/
    loaders.py
    normalize.py
    pipeline.py
  storage/
    repository.py
    indexes.py
  retrieval/
    query.py
    rank.py
  mirror/
    prompts.py
    orchestrator.py
    guards.py
  personas/
    definitions.py
    graph.py
    synthesis.py
  memory/
    candidates.py
    review.py
  proactive/
    scheduler.py
    candidates.py
    relevance.py
    outbox.py
  notifications/
    adapters.py
    email.py
    macos.py
    links.py
  evals/
    cases.py
    scoring.py
tests/
  unit/
  integration/
  fixtures/
examples/
  private/
```

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
