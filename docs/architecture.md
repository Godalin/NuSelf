# NuSelf Architecture

NuSelf is an AI mirror for one person's ideas, memory, experience, and reasoning habits. The system should help people continue a deep conversation when the original person is unavailable, while making clear what is recalled evidence, inferred stance, and newly generated reasoning.

## Product Principles

- Personal fidelity first: answers should preserve the person's concepts, vocabulary, values, and uncertainty.
- Traceable reasoning: when possible, the system should point back to source memories, notes, conversations, or derived profiles.
- Clear epistemic status: separate direct source material, stable profile knowledge, model inference, and speculation.
- Incremental growth: every ingestion, profile update, and evaluation path should be testable as a small component.
- Local-first core: the project should be usable as a standard Python application before adding hosted services.

## System Shape

The initial implementation should be a modular Python application managed by `uv`.

```text
User Interface
  -> Conversation Service
    -> Retrieval Layer
    -> Mirror Profile
    -> Response Orchestrator
    -> Safety and Epistemic Guards
  -> Memory Update Pipeline
    -> Source Ingestion
    -> Normalization
    -> Indexing
    -> Profile Distillation
  -> Evaluation Suite
```

## Core Modules

### Source Ingestion

Ingests raw personal material such as notes, essays, chat exports, bookmarks, timelines, and manually written profile facts.

Responsibilities:

- Load source documents from local files.
- Preserve source metadata such as title, date, origin, author, and privacy level.
- Split material into stable chunks without losing citation context.
- Reject malformed input with explicit validation errors.

### Knowledge Store

Stores normalized source chunks and derived profile artifacts.

Responsibilities:

- Keep raw source references immutable once imported.
- Maintain searchable indexes for retrieval.
- Store derived facts, preferences, recurring claims, and known uncertainties separately from raw source text.
- Support re-indexing without changing source identity.

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

### Response Orchestrator

Coordinates model calls and deterministic checks.

Responsibilities:

- Assemble prompts from typed inputs rather than ad hoc strings spread across the codebase.
- Enforce output schemas for answer text, cited evidence, uncertainty, and follow-up questions.
- Run post-generation checks for unsupported claims and missing citations.
- Keep provider-specific model code behind a narrow adapter boundary.

### Memory Update Pipeline

Turns new conversations or new documents into candidate profile updates.

Responsibilities:

- Propose memory/profile changes without silently committing them.
- Record why a profile item was added, changed, or rejected.
- Allow human review before durable personal facts are updated.
- Keep conversation-derived memory lower confidence than direct authored sources unless reviewed.

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
  memory/
    candidates.py
    review.py
  evals/
    cases.py
    scoring.py
  cli.py
tests/
  unit/
  integration/
  fixtures/
```

## Data Model Boundaries

Use typed domain models for all boundaries between modules.

Important entities:

- `SourceDocument`: original imported material plus metadata.
- `SourceChunk`: indexed excerpt with source location.
- `EvidenceRef`: pointer from an answer or profile item back to source material.
- `ProfileItem`: durable belief, preference, life fact, style trait, or uncertainty.
- `ConversationTurn`: normalized user/assistant exchange.
- `MirrorResponse`: answer text plus evidence, confidence, and epistemic status.
- `MemoryCandidate`: proposed update created from new material or conversation.

## Trust And Safety Boundaries

NuSelf should avoid pretending to be the person in contexts where that would be misleading. The product can speak as a mirror or simulation, but the implementation should preserve metadata that lets interfaces disclose the nature of the response.

Required guardrails:

- Do not invent private facts when no source supports them.
- Mark inferred answers as inference.
- Prefer "I do not have enough evidence" over confident fabrication.
- Keep high-impact advice, medical/legal/financial claims, and interpersonal escalation cautious and source-aware.
- Keep raw private sources and derived summaries separated so future permission controls are possible.

## Initial Technical Choices

- Python package managed by `uv`.
- Static type checking with `uvx pyright`.
- Pydantic or dataclasses for typed domain models.
- A local file-backed store for the first version, with repository interfaces that can later support SQLite or vector databases.
- Provider adapters for LLM calls, with no provider-specific code in domain modules.
- Tests grouped by sub-component so ingestion, retrieval, profile logic, and orchestration can be validated independently.

