# Current Goal

This file is the short-term progress guide for NuSelf. It narrows the next implementation phase so day-to-day work does not sprawl across the whole roadmap.

## Focus

Add profile item search and query commands.

## Status

Recently completed foundation slice:

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

## Scope

- Add search and filter commands for derived profile items.

## Not Now

- Symbolic graph implementation.
- Plugin loading.
- Full decay and reflection rule execution.
- Vector or graph indexes.
- Proactive reflection and notification work.
- Web or GUI interface work.
- Full automatic conflict resolution.
- Derived vector or graph indexes.
- Automatic citation synthesis from imported source documents.
- Symbolic graph implementation.
- Derived vector or graph indexes over ingested sources.
- Fully automatic background processing of imported source chunks.
- Persona/profile prompt synthesis from profile items.

## Completion Criteria

- Profile item models and repository serialize round-trip.
- Source-derived candidates include structured source evidence records.
- CLI commands expose the candidate extraction/review path without committing durable memory directly.
- README TODOs and planning docs reflect the source-to-candidate and deletion slices before moving to broader profile synthesis.
