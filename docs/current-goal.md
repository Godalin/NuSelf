# Current Goal

This file is the short-term progress guide for NuSelf. It narrows the next implementation phase so day-to-day work does not sprawl across the whole roadmap.

## Focus

Build the open symbolic graph foundation: relation links are now inspectable, and the next slice should move relation behavior into `RelationDescriptor` definitions.

## Status

Recently completed retrieval foundation slice:

- `MemoryEntry` now has a clear migration path into a `MemoryObject` envelope.
- `MemoryTypeRegistry` validates descriptor-backed memory objects.
- Core descriptors cover `belief`, `preference`, `episode`, and `instruction`.
- Existing file-backed memory entries remain inspectable and usable during migration.
- Curator and optimizer writes pass through repository-level descriptor validation.
- Chat now triggers memory curation after turns, so conversation is the primary memory source.
- Memory curation now uses discussion depth, quality, and durable signal instead of fixed turn-count gating.
- Thread curation cursors now use absolute message indexes so compression does not skip later memory updates.
- Manual `memory add` now infers type, title, tags, and confidence through a memory intake agent.
- Memory candidates are now file-backed, inspectable, reviewable, and carry real-world temporal fields.
- Candidate `accept`, `edit`, `merge`, and `reject` commands now exist and accepted memories pass through descriptor validation.
- Curator and optimizer proposals now create inspectable candidates instead of directly mutating durable memory.
- Memory entries and candidates now carry structured source-linked evidence records.
- Memory and candidate detail commands now show evidence records.
- `memory stats` now reports type, review, candidate, evidence, and temporal coverage.
- `memory search` now supports deterministic filters for type, tag, review state, observed time, and valid time.
- Profile items now live in a file-backed repository and are inspectable as derived profile state.
- Imported source chunks now expand into reviewable `profile_fact` candidates with source-linked evidence.
- Raw private source deletion now cascades to derived candidates and profile items.
- `memory source delete` and `memory profile delete` now make derived cleanup explicit.
- `memory profile search` now supports deterministic filters for type, tag, observed time, valid time, and text queries.
- Built-in `goal` and `concept` memory types now validate through the descriptor registry.
- `memory add`, curator, optimizer, and intake parser paths now recognize `goal` and `concept`.
- Source document and chunk models now serialize round-trip.
- Markdown and plain text files can be ingested into ignored `private/sources/`.
- Source front matter now preserves title, date, tags, origin, and privacy.
- Ingested chunks now keep stable `source:<source-id>:<chunk-index>` references.
- `memory source ingest`, `list`, `show`, and `chunks` expose local source ingestion from the CLI.
- `memory source search` now returns matching chunks with source refs and document metadata.
- `memory reindex` now rebuilds `private/derived/source_index.json` from authoritative source records.
- `MemoryQueryService` now packs matching source chunks alongside durable memory entries.
- The default chat agent now includes relevant source chunks in its memory context.
- `MemoryQueryService` now also packs derived profile items alongside durable memory entries and source chunks.
- The default chat agent now includes relevant profile items in its memory context.
- The memory intake, curator, and optimizer prompts now include relevant derived profile items.
- Chat now returns structured response metadata and flags unsupported personal claims when evidence is missing.
- The chat agent now exposes `search_memory` tool that can be invoked to explicitly search memory entries, profiles, and sources.
- Tool calls are parsed from LLM responses and executed, with results returned for LLM processing.
- `MemoryQueryService` now applies descriptor-aware type affinity, exposes type/tag filters, and surfaces simple relation metadata in packed memory context.
- `MemoryQueryService` now expands direct matches through existing `related_memory_ids` and `supersedes` links, including reverse `related_by` and `superseded_by` matches.
- `memory reindex` now rebuilds `private/derived/relation_index.json` from authoritative memory links.
- `memory relations` now inspects the derived relation index with relation/source/target filters.
- `RelationDescriptorRegistry` now defines built-in `supersedes` and `related_to` relation behavior.
- Relation index records now include descriptor-derived metadata such as inverse relation, symmetry, temporal policy, confidence policy, and retrieval rule.

## Scope

- Built-in relation descriptors and descriptor-backed relation index generation are ready.
- Next focus is optional: add more relation descriptors or design the first symbolic node/edge graph projection.
- Keep the graph layer derived and rebuildable from authoritative memory entries.
- Keep relation inspection commands working while descriptor metadata grows.

## Not Now

- Full LangGraph integration (requires refactoring chat agent architecture).
- Full symbolic graph storage beyond the existing derived relation index.
- Plugin loading.
- Full decay and reflection rule execution.
- Vector or graph indexes.
- Proactive reflection and notification work.
- Web or GUI interface work.
- Full automatic conflict resolution.
- Derived vector or graph indexes.
- Automatic citation synthesis from imported source documents.
- Derived vector or graph indexes over ingested sources.
- Fully automatic background processing of imported source chunks.
- Persona/profile prompt synthesis from profile items.

## Completion Criteria

- `RelationDescriptor` and relation registry types exist in the memory domain layer.
- Built-in descriptors cover `supersedes` and `related_to`.
- Relation index records include descriptor-derived metadata.
- Repository and CLI tests cover descriptor-backed relation index generation and inspection.
- README TODOs track the descriptor registry as complete.
- All chat agent and daemon tests pass.
