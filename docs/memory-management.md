# Memory Management Plan

NuSelf should treat memory as the product core, not as a chat-session helper. The mirror simulates a continuous person-like mind: it should remember across all interactions, revise itself when evidence changes, and keep important context available without requiring the user to choose or name sessions.

## Research Summary

Mainstream agent frameworks converge on the same split:

- Recent conversation state is useful, but it is not enough for long-lived agents.
- Long-term memory must live outside the context window and be recalled selectively.
- The best systems separate always-visible core memory from searchable archival memory.
- Memory writes need management: extraction, consolidation, update, deletion, confidence, and provenance.
- Retrieval quality depends on query planning and ranking, not only the storage backend.

Relevant current patterns:

- LangChain/LangGraph separates short-term thread memory from long-term memory. Long-term memory is stored in LangGraph Stores as JSON documents under namespaces and keys, and tools can read/write through the runtime store. This fits NuSelf's need for cross-thread memory, but NuSelf should not make LangGraph thread IDs the product-level memory boundary.
- LangMem adds memory managers and tools on top of LangGraph Store. It supports semantic, episodic, and procedural memory patterns, plus hot-path tools and background extraction. This is the closest match to NuSelf's preferred LangChain ecosystem.
- Letta/MemGPT emphasizes memory hierarchy: core memory in context, recall/conversation history, and archival memory outside context. The important lesson is that agents actively manage memory through tools, rather than only passively retrieving RAG chunks.
- Zep/Graphiti models memory as a temporal knowledge graph. This is valuable for NuSelf because personal memory changes over time and contradictions should be represented instead of overwritten blindly.
- LlamaIndex Memory uses short-term FIFO memory plus long-term memory blocks such as static blocks, fact extraction blocks, and vector blocks. Its memory-block priority model is useful, but it is more retrieval/index oriented than NuSelf's desired LangGraph orchestration.
- CrewAI's newer unified Memory API uses LLM-assisted scope/category/importance inference and composite recall scoring. This reinforces the need for importance, recency, and semantic relevance in NuSelf ranking, even if CrewAI is not the main runtime.

Sources:

- LangChain long-term memory: https://docs.langchain.com/oss/python/langchain/long-term-memory
- LangChain memory concepts: https://docs.langchain.com/oss/python/concepts/memory
- LangMem overview: https://langchain-ai.github.io/langmem/
- LangMem semantic memory guide: https://langchain-ai.github.io/langmem/guides/extract_semantic_memories/
- LangMem memory tools guide: https://langchain-ai.github.io/langmem/guides/memory_tools/
- Letta memory overview: https://docs.letta.com/guides/agents/memory
- Letta MemGPT architecture: https://docs.letta.com/guides/agents/architectures/memgpt
- Zep Graphiti overview: https://help.getzep.com/graphiti/graphiti/overview
- LlamaIndex memory guide: https://docs.llamaindex.ai/en/stable/module_guides/deploying/agents/memory/
- CrewAI memory: https://docs.crewai.com/en/concepts/memory

## NuSelf-Specific Position

NuSelf does not have ordinary sessions. It has one continuous private memory space with many interaction surfaces:

- CLI conversations.
- Background daemon thoughts.
- Imported notes and source documents.
- Memory review decisions.
- Future email/macOS notification discussions.
- Persona discussions between thought selves.

Therefore, memory retrieval should answer: "What should this mirror remember now?" not "What happened in this session?"

Design consequences:

- The root `private/` memory store is authoritative.
- The default conversation thread is shared working memory for the current NuSelf mind, not an isolated session.
- Future non-default `thread_id` values can create branches for experiments or separate topics, but those branches should share long-term memory unless explicitly sandboxed.
- Conversation threads are event history and evidence, not the main identity boundary.
- Every durable claim needs provenance, confidence, timestamps, and review state.
- Contradictions are first-class. New evidence should supersede, qualify, or conflict with older entries rather than silently delete them.
- User-visible memory entries remain inspectable and editable. Derived vector, lexical, and graph indexes are rebuildable artifacts.
- The model should not be allowed to write durable personal memory directly. It proposes candidates; deterministic code and human review decide what becomes durable.

## Memory Layers

### 1. Raw Evidence

Raw evidence is the immutable or append-only material from which memories are derived.

Storage:

- `private/sources/`: imported notes, documents, essays, exports.
- `private/threads/`: normalized conversation turns and summaries.
- `private/logs/`: daemon and proactive event logs when relevant.

Responsibilities:

- Preserve original text and source metadata.
- Provide stable evidence references.
- Support reprocessing when schemas or extractors improve.

### 2. Episodic Memory

Episodic memory records what happened in interactions.

Examples:

- "We discussed why NuSelf should avoid session boundaries."
- "The user corrected the architecture toward OpenAI env variable names."
- "A proactive thought was dismissed as not useful."

Use:

- Reconstruct past discussions.
- Learn interaction patterns.
- Feed background reflection.
- Provide evidence for semantic or procedural memory candidates.

Storage:

- Start with `private/threads/*.json` plus derived episode records under `private/memory/episodes/`.
- Later add vector and temporal indexes under `private/derived/`.

The default `private/threads/default.json` is the shared working memory stream for all terminals attached to the same NuSelf mind. Multiple terminals should read and write this stream with a lock. Branch threads are a future feature and should be treated as alternate working-memory streams, not separate people.

### 3. Semantic Memory

Semantic memory stores facts, beliefs, preferences, relationships, and open questions.

Examples:

- Profile facts.
- Durable beliefs.
- Recurring interests.
- Technical preferences.
- Known contradictions or uncertainty.

Storage:

- Current `MemoryEntry` records under `private/memory/entries/`.
- Add fields for `evidence_refs`, `valid_from`, `valid_until`, `supersedes`, `contradicts`, `importance`, and `last_used_at`.

Retrieval:

- Lexical search for precise terms.
- Vector search for conceptual relevance.
- Metadata filtering by type, tag, review state, privacy, confidence, and time.
- Optional graph search for entity relationships and contradictions.

### 4. Procedural Memory

Procedural memory controls how NuSelf behaves.

Examples:

- Communication style.
- User-specific preferences for depth, language, and directness.
- Persona rules.
- Memory write policy.
- Notification policy.

Storage:

- Reviewed `instruction` and `style_trait` memory entries.
- Future prompt/profile blocks under `private/profile.md` or `private/memory/procedural/`.

Use:

- Always-visible core profile.
- Persona prompts.
- Retrieval and notification policy.

### 5. Core Profile

Core profile is the small always-visible identity layer.

It should be compact, curated, and loaded into most conversations:

- Who the mirror is simulating.
- Stable worldview/style notes.
- High-confidence constraints.
- Current open tensions that shape answers.

The core profile is not a replacement for retrieval. It is the executive summary of the memory system.

## Write Pipeline

Memory writes should be explicit and auditable:

```text
new conversation turn or source import
  -> candidate extractor
  -> duplicate/conflict search
  -> candidate record
  -> optional curator agent expansion
  -> human review or policy gate
  -> durable MemoryEntry update
  -> rebuild derived indexes
```

Hot-path writes:

- Extract obvious low-risk candidates after a chat turn.
- Never block the user-facing answer on expensive memory consolidation.
- Store candidates as draft/review records.

Background writes:

- Batch process conversation windows.
- Merge duplicates.
- Detect contradictions.
- Distill profile updates.
- Propose procedural updates when the user repeatedly corrects behavior.
- Run periodically in the daemon when the working-memory stream is dirty.
- Run when an interactive attachment exits, so useful discussion does not remain only in short-term working memory.
- Defer when the curator agent is unavailable or returns invalid structure; do not use a local raw-transcript fallback.
- Ignore trivial greetings, name pings, acknowledgements, and other low-value chatter.
- Prefer updating or refining existing memories over creating duplicates when the same idea is already represented.

The background writer should be a dedicated Memory Curator Agent. The conversation agent writes turns; the curator decides whether to create, update, supersede, or ignore long-term memories.

Deletion and forgetting:

- User delete commands remove or tombstone durable entries.
- Derived indexes must be rebuildable after deletion.
- If a memory is derived from raw private sources, deletion policy must clarify whether only the derived memory is deleted or the source evidence is also removed.

## Query Pipeline

NuSelf should use a dedicated memory query module before generation.

```text
user input
  -> query analyzer
  -> retrieval plan
  -> memory searches
  -> reranking
  -> context packing
  -> answer generation with evidence metadata
```

The query analyzer decides:

- Whether the request needs personal memory.
- Which memory types are relevant: semantic, episodic, procedural, source chunks, graph relations.
- Whether to search broad memory, recent interaction history, or specific tags/entities.
- Whether evidence is required before making a personal claim.

The retriever should combine:

- Core profile.
- Recent working context.
- Reviewed high-confidence semantic memory.
- Relevant episodes.
- Source evidence.
- Open questions and contradictions.

The packer enforces a budget:

- Always include the minimal core profile.
- Prefer reviewed and high-confidence entries.
- Include citations/evidence refs, not just summaries.
- Include conflicting memories when they affect the answer.
- Keep raw conversation history small unless the user asks for reconstruction.

## Memory Query Agent vs Tool

NuSelf should implement both a deterministic service and agent-facing tools.

### Deterministic Service

`MemoryQueryService` should be callable by the conversation orchestrator.

Inputs:

- User query.
- Current turn metadata.
- Optional persona scope.
- Budget and evidence policy.

Outputs:

- Packed memory context.
- Ranked result list.
- Evidence refs.
- Omitted-but-relevant candidates for debugging.

This service should be testable without LLM calls.

### Agent Tool

Expose memory search as tools to the model:

- `search_memory(query, types, tags, time_range, limit)`.
- `show_memory(entry_id)`.
- `propose_memory(candidate)`.
- `search_episodes(query, time_range, limit)`.
- `search_sources(query, limit)`.

The user-facing agent can use search tools when it realizes it needs more context. Write tools should create candidates, not directly commit durable memory.

### Memory Curator Agent

Use a separate curator agent for write management:

- Extract candidates from conversations and sources.
- Search existing memory before creating new entries.
- Propose merges, updates, contradictions, and deletions.
- Produce structured candidate records.
- Apply low-risk episode memories automatically when policy allows.
- Keep semantic and procedural updates as draft or low-confidence entries until the review model is mature.
- Write each applied action to `private/logs/memory.log`.
- Reject proposed memory bodies that look like raw chat transcripts.

The curator can run in the background. It should not produce user-facing text.

This matches LangMem's memory-manager-agent pattern while preserving NuSelf's user-review and file-backed source-of-truth requirements.

### Memory Optimizer Agent

Use a separate optimizer agent for low-frequency maintenance of existing long-term memory:

- Review current entries in bounded batches, not one isolated agent call per entry.
- Merge duplicate or overlapping entries by updating the strongest surviving entry with the consolidated summary.
- Delete weaker duplicate entries only when their useful content is fully represented by the updated survivor.
- Ignore entries that are already clear, unique, or too risky to rewrite.
- Rewrite messy entries into concise summaries instead of preserving transcript-shaped text.
- Do not create new entries during optimization; this pass cleans existing memory rather than extracting new memory.
- Defer the run when the optimizer agent is unavailable or returns invalid output.
- Log every applied update or deletion to `private/logs/memory.log`.

This task is intentionally lower frequency than conversation curation. It is for cleaning accumulated memory drift, not for processing every chat turn.

## LangChain/LangGraph Fit

LangChain/LangGraph can implement this design.

Use LangGraph for:

- Conversation graph.
- Background memory-curation graph.
- Proactive reflection graph.
- Human review interrupts or gates.
- Long-running daemon workflows.

Use LangGraph Store for:

- Derived long-term memory indexes once the local file model stabilizes.
- Namespaces such as `("person", "semantic")`, `("person", "episodes")`, `("person", "procedural")`, `("sources", source_id)`, and `("personas", persona_id)`.

Use LangGraph checkpointers only for:

- Debuggable graph execution state.
- Resumable tool runs.
- Temporary working state.

Do not use checkpointer thread memory as NuSelf's main memory system, because NuSelf intentionally does not make sessions the conceptual boundary.

Use LangMem for:

- Candidate extraction from messages.
- Memory manager tools.
- Semantic, episodic, and procedural extraction patterns.
- Background consolidation once the MemoryEntry schemas stabilize.

Keep NuSelf-owned code for:

- File-backed authoritative entries.
- Review state machine.
- Evidence references.
- Deletion policy.
- Export/share bundles.
- Privacy and provenance rules.

## Storage Strategy

Phase 1: File-backed authoritative memory.

- Keep `private/memory/entries/*.json` as source of truth.
- Add `private/memory/candidates/*.json`.
- Add `private/memory/episodes/*.json`.
- Keep `private/derived/` rebuildable.

Phase 2: Local indexes.

- Lexical index for deterministic search.
- Embedding index for semantic retrieval.
- Optional SQLite metadata table for filtering and ranking.

Phase 3: Temporal graph.

- Add entity/relation extraction for people, projects, beliefs, places, concepts, and artifacts.
- Track validity intervals and supersession.
- Consider Graphiti if NuSelf needs high-quality temporal graph search before building its own.

Phase 4: LangGraph Store bridge.

- Mirror reviewed entries into LangGraph Store namespaces.
- Keep file-backed records authoritative.
- Use store/search tools inside LangGraph agents.

## Ranking Signals

Memory ranking should combine:

- Semantic relevance.
- Lexical match.
- Recency.
- Importance.
- Review state.
- Confidence.
- Source reliability.
- Persona scope.
- Prior usage success.
- Contradiction relevance.

Recommended first scoring shape:

```text
score =
  semantic_weight * semantic_similarity
  + lexical_weight * lexical_match
  + recency_weight * recency_decay
  + importance_weight * importance
  + confidence_weight * confidence
  + review_bonus
  - stale_penalty
```

Keep ranking explainable. Returned results should include match reasons.

## CLI Surface

Extend existing `nuself memory` commands before adding complex UI:

```text
nuself memory candidates list
nuself memory candidates show <candidate-id>
nuself memory candidates accept <candidate-id>
nuself memory candidates reject <candidate-id>
nuself memory candidates merge <candidate-id> <entry-id>

nuself memory query "..."
nuself memory graph search "..."
nuself memory episodes search "..."
nuself memory stats
```

The chat agent should eventually show memory citations on demand:

```text
:mem
:mem last
:mem why
```

## Implementation Roadmap

### Slice 1: Memory Candidate Store

- Add `MemoryCandidate` domain model.
- Add file-backed candidate repository.
- Add CLI list/show/accept/reject commands.
- Add tests for candidate lifecycle.

### Slice 1A: Automatic Episode Curator

- Add a shared working-memory lock around `private/threads/default.json`.
- Add a cursor that records which conversation turns have been summarized.
- Add a Memory Curator Agent that periodically summarizes new turns into an `episode` memory entry.
- Trigger the curator when interactive chat exits.
- Log every memory update to `private/logs/memory.log`.

### Slice 2: Conversation-To-Candidate Extraction

- After each chat turn, run a lightweight candidate extractor.
- Start deterministic and conservative.
- Store candidates as drafts; do not auto-commit personal facts.

### Slice 3: Memory Query Service

- Implement typed query input and result output.
- Search existing entries with lexical matching first.
- Return match reasons and evidence refs.
- Replace the temporary chat agent's "load first 24 entries" behavior with query-driven retrieval.

### Slice 4: Context Packer

- Build a memory context budgeter.
- Always include core profile.
- Include ranked memories with ids and evidence.
- Include conflicts when relevant.

### Slice 5: LangMem Prototype

- Add an optional LangMem-based curator behind an interface.
- Use fake model tests for schema and control flow.
- Keep all LangMem outputs as candidates, not committed entries.

### Slice 6: Derived Indexes

- Add lexical index and metadata stats under `private/derived/`.
- Add embedding index only after query service behavior is stable.
- Make `memory reindex` rebuild all derived artifacts.

### Slice 7: Temporal Memory

- Add fields for validity and supersession.
- Add contradiction detection.
- Evaluate Graphiti integration against local file-backed needs.

## Immediate Design Decision

For NuSelf, choose this architecture:

```text
Authoritative memory:
  private/memory/entries/
  private/memory/candidates/
  private/memory/episodes/
  private/memory/cursors/

Derived retrieval:
  private/derived/lexical_index.json
  private/derived/embedding_index/
  private/derived/graph/

Runtime agents:
  conversation agent
  memory query service/tool
  memory curator agent
  proactive reflection agent
```

This keeps personal memory inspectable and editable while allowing LangChain/LangGraph to provide orchestration, stores, tools, and background memory processing.
