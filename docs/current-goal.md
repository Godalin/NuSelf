# Current Goal

This file is the short-term progress guide for NuSelf. It narrows the next implementation phase so day-to-day work does not sprawl across the whole roadmap.

## Focus

Add local source ingestion for Markdown and plain text.

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
- Built-in `goal` and `concept` memory types now validate through the descriptor registry.
- `memory add`, curator, optimizer, and intake parser paths now recognize `goal` and `concept`.

## Scope

- Add file-backed source document records under ignored `private/sources/`.
- Add Markdown and plain text loaders.
- Preserve source metadata: title, path, date, tags, origin, and privacy.
- Add chunking that keeps stable source references.
- Add a CLI command to ingest a local file or directory into the development store.

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

## Completion Criteria

- Source document and chunk models serialize round-trip.
- Markdown and plain text ingestion are covered by tests.
- Ingested chunks preserve source references.
- README TODOs and planning docs reflect the completed ingestion slice before moving to the next goal.
