# NuSelf Development Plan

This plan turns the architecture into small, testable milestones. Each milestone should leave the project runnable and type-checkable with `uvx pyright`.

## Development Policy

- Build against the current design, not historical interfaces.
- Do not add compatibility layers for old CLI commands, protocol fields, schemas, or Python APIs during this development phase.
- When a boundary changes, update every caller, test, example, and document in the same milestone.
- Prefer aggressive refactoring over incremental compatibility when it makes the architecture clearer.
- Keep each milestone validated with tests and `uvx pyright`.
- User-facing functionality, commands, configuration, and runtime behavior changes must update both `README.md` and `README.zh-CN.md`.

## Milestone 0: Project Skeleton

Goal: create the minimum Python project structure.

Deliverables:

- `pyproject.toml` configured for a standard `uv` project.
- `src/nuself/` package with empty module boundaries matching the architecture.
- `tests/` layout with a basic smoke test.
- Developer commands documented in `AGENTS.md`.
- `.gitignore` entry for root `private/`.
- Committed `examples/private/` sample directory for tests, demos, and sharing format documentation.
- CLI entrypoint placeholder for `nuself`.

Validation:

- `uv run pytest`
- `uvx pyright`

## Milestone 1: CLI And Daemon Skeleton

Goal: establish the command-line control surface and local daemon lifecycle before implementing the full agent.

Deliverables:

- `nuself daemon start`, `stop`, `status`, and `logs` command shapes.
- Daemon runtime paths under `private/runtime/` and logs under `private/logs/`.
- Unix domain socket server with a minimal JSONL protocol.
- Daemon client with health check and typed error handling.
- `nuself chat` command that can attach to a running daemon or run a one-shot fake runtime.

Validation:

- Unit tests for protocol request/response models.
- Lifecycle tests using temporary private roots.
- CLI tests for daemon status when no daemon is running.
- Fake attached chat test without model calls.

## Milestone 2: Typed Domain Model

Goal: define the core data contracts before implementing behavior.

Deliverables:

- Model for the memory root manifest.
- Models for source documents, chunks, evidence references, profile items, memory entries, conversation turns, thread records, mirror responses, and memory candidates.
- Serialization tests for each model.
- Explicit enums or literals for source type, confidence level, epistemic status, and privacy level.

Validation:

- Unit tests for model validation and round trips.
- `uvx pyright` passes with strict-enough settings for the new package.

## Milestone 3: Memory Entry Management

Goal: make private memory inspectable and editable as clear entries.

Deliverables:

- File-backed `MemoryEntry` repository under `private/memory/entries/`.
- CLI commands for `memory list`, `show`, `add`, `edit`, `delete`, `search`, and `reindex`.
- Review queue commands for accepting, editing, merging, and rejecting candidates.
- Derived indexes under `private/derived/`.
- Memory management design aligned with [docs/memory-management.md](memory-management.md).

Validation:

- Repository CRUD tests with temporary private roots.
- CLI tests for list/show/delete flows.
- Tests that deleted entries disappear from derived indexes after reindex.
- Review flow tests for accept, edit, merge, and reject.

## Milestone 4: Local Ingestion Pipeline

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

## Milestone 5: File-Backed Knowledge Store

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

## Milestone 6: Retrieval Layer

Goal: retrieve relevant evidence for a user question.

Deliverables:

- Query model.
- Baseline lexical retrieval.
- Ranking hooks for future embedding or hybrid search.
- Returned evidence references with source metadata.
- `MemoryQueryService` that replaces prompt-wide loading of all memory entries.
- Context packer with budget, ranking explanations, and contradiction inclusion.

Validation:

- Deterministic retrieval tests with small fixtures.
- Tests for empty results and ambiguous queries.
- Tests for memory ranking reasons and context budget behavior.

## Milestone 7: Mirror Response Orchestration

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

## Milestone 8: Lightweight Persona Subgraphs

Goal: support bounded discussion between multiple thought selves.

Deliverables:

- LangGraph-based persona subgraph with routed persona nodes.
- Persona definitions for analyst, skeptic, builder, historian, care, and synthesizer.
- Structured output schema for persona contributions.
- Synthesizer that creates the only user-facing response from persona outputs.
- Configuration that limits persona count and critique rounds by default.

Validation:

- Unit tests with fake model outputs for each persona.
- Routing tests proving only relevant personas run.
- Tests that final responses come from the synthesizer.
- Tests that unsupported persona claims are marked as inference or rejected.

## Milestone 9: Memory Candidate Review

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

## Milestone 10: Proactive Agent And Outbox

Goal: let NuSelf surface new ideas without becoming a noisy chatbot.

Deliverables:

- Reflection scheduler interface for time-based and event-based triggers.
- Randomized low-frequency daemon self-reflection events with cooldowns and quiet hours.
- Idea candidate generator over recent threads, private memory, and new sources.
- Relevance gate with novelty, confidence, urgency, cooldown, and interruption-cost fields.
- Notification outbox with idempotency keys and delivery status.
- macOS notification adapter stub.
- Email adapter stub.
- Deep link model for creating a new thread or opening an existing thread.

Validation:

- Scheduler tests with fake time.
- Random trigger tests proving cooldowns and quiet hours are enforced.
- Candidate generation tests with fixture memory and threads.
- Relevance gate tests for low-value, duplicate, urgent, and cooldown cases.
- Outbox tests proving graph nodes write intents without sending external notifications.
- Adapter tests using fakes instead of real email or system notifications.

## Milestone 11: Notification Adapters

Goal: deliver interesting daemon thoughts through controlled channels.

Deliverables:

- Log-only notification adapter.
- macOS notification adapter.
- Email adapter using ignored private configuration.
- Deep link or command payload that opens a new or existing thread.
- Outbox commands for list, show, send, and dismiss.

Validation:

- Adapter tests with fakes or dry-run mode.
- Tests that graph nodes never send notifications directly.
- Tests that outbox delivery records attempts, failures, and success.
- Tests that deep links resolve to a thread or new thread seed.

## Milestone 12: Evaluation Harness

Goal: prevent regressions in fidelity and uncertainty behavior.

Deliverables:

- Golden conversation fixtures.
- Scoring helpers for citation coverage, unsupported personal claims, and uncertainty handling.
- Local evaluation command.

Validation:

- Evaluation command runs on fixtures without external services by using fake or recorded providers.
- Regression tests fail when citations disappear from evidence-required answers.
- Persona evaluation cases cover disagreement, synthesis, and overconfidence.
- Proactive evaluation cases cover notification relevance and non-interruption behavior.

## Milestone 13: First Usable Interface

Goal: expose the mirror through a practical local interface.

Deliverables:

- CLI chat command or minimal local web interface.
- `nuself attach` for connecting to an existing daemon conversation.
- Conversation history persistence.
- Source/citation display in the interface.
- Thread links that can open a proactive candidate as a new or existing conversation.
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
- Keep LangGraph as the default runtime unless a documented milestone requires a different framework.
- Keep persona discussion bounded and routed to avoid unnecessary cost and noisy outputs.
- Keep notification delivery behind an outbox so tests never send real messages.
- Update `docs/architecture.md` when implementation changes the intended boundaries.
