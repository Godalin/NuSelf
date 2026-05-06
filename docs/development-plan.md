# NuSelf Development Plan

This plan turns the architecture into small, testable milestones. Each milestone should leave the project runnable and type-checkable with `uvx pyright`.

## Milestone 0: Project Skeleton

Goal: create the minimum Python project structure.

Deliverables:

- `pyproject.toml` configured for a standard `uv` project.
- `src/nuself/` package with empty module boundaries matching the architecture.
- `tests/` layout with a basic smoke test.
- Developer commands documented in `AGENTS.md`.
- `.gitignore` entry for root `private/`.
- Committed `examples/private/` sample directory for tests, demos, and sharing format documentation.

Validation:

- `uv run pytest`
- `uvx pyright`

## Milestone 1: Typed Domain Model

Goal: define the core data contracts before implementing behavior.

Deliverables:

- Model for the memory root manifest.
- Models for source documents, chunks, evidence references, profile items, conversation turns, mirror responses, and memory candidates.
- Serialization tests for each model.
- Explicit enums or literals for source type, confidence level, epistemic status, and privacy level.

Validation:

- Unit tests for model validation and round trips.
- `uvx pyright` passes with strict-enough settings for the new package.

## Milestone 2: Local Ingestion Pipeline

Goal: import local personal material into normalized source records.

Deliverables:

- Default memory-root discovery for root `private/`.
- Explicit override support for `examples/private/`.
- Plain-text and Markdown loaders.
- Metadata handling for title, path, date, and tags.
- Chunking that preserves source references.
- CLI command to ingest a local directory into a development store.

Validation:

- Discovery tests for missing, invalid, private, and example memory roots.
- Loader tests with fixture files.
- Chunk boundary tests.
- Error tests for malformed metadata.

## Milestone 3: File-Backed Knowledge Store

Goal: persist source documents, chunks, and profile artifacts locally.

Deliverables:

- Repository interface for documents, chunks, profile items, and memory candidates.
- JSONL or SQLite implementation for local development.
- Store paths resolved relative to the active memory root.
- Re-index command that can rebuild derived indexes from raw sources.

Validation:

- Repository contract tests.
- Re-index idempotence test.
- Tests proving raw source identifiers remain stable.

## Milestone 4: Retrieval Layer

Goal: retrieve relevant evidence for a user question.

Deliverables:

- Query model.
- Baseline lexical retrieval.
- Ranking hooks for future embedding or hybrid search.
- Returned evidence references with source metadata.

Validation:

- Deterministic retrieval tests with small fixtures.
- Tests for empty results and ambiguous queries.

## Milestone 5: Mirror Response Orchestration

Goal: generate source-aware mirror responses from typed context.

Deliverables:

- Prompt assembly module.
- LLM provider adapter interface.
- Response schema with answer text, evidence references, confidence, and epistemic status.
- Unsupported-claim guard that flags answers with no evidence when evidence is required.

Validation:

- Unit tests with a fake provider.
- Schema validation tests.
- Guard tests for unsupported personal claims.

## Milestone 6: Memory Candidate Review

Goal: convert new documents and conversations into reviewable profile updates.

Deliverables:

- Candidate generation from source chunks and conversation turns.
- Review state machine: proposed, accepted, rejected, superseded.
- Audit trail for every accepted profile item.
- Export command that writes curated share bundles under `private/shares/`.

Validation:

- Candidate lifecycle tests.
- Tests for preserving contradictory evidence.
- Tests that conversation-derived facts are lower confidence by default.
- Share bundle tests proving exports include only explicitly selected records.

## Milestone 7: Evaluation Harness

Goal: prevent regressions in fidelity and uncertainty behavior.

Deliverables:

- Golden conversation fixtures.
- Scoring helpers for citation coverage, unsupported personal claims, and uncertainty handling.
- Local evaluation command.

Validation:

- Evaluation command runs on fixtures without external services by using fake or recorded providers.
- Regression tests fail when citations disappear from evidence-required answers.

## Milestone 8: First Usable Interface

Goal: expose the mirror through a practical local interface.

Deliverables:

- CLI chat command or minimal local web interface.
- Conversation history persistence.
- Source/citation display in the interface.
- Configuration for model provider credentials outside committed files.

Validation:

- Manual smoke test of ingestion plus one conversation.
- Integration test with fake provider.
- `uv run pytest` and `uvx pyright`.

## Cross-Cutting Work

- Keep all module boundaries typed.
- Add tests with each component instead of deferring testing to the end.
- Keep provider-specific behavior behind adapters.
- Keep raw sources, derived profile state, and conversation logs separate.
- Keep real `private/` ignored and out of commits.
- Keep `examples/private/` public, minimal, and safe to publish.
- Update `docs/architecture.md` when implementation changes the intended boundaries.
