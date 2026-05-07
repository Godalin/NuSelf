# Current Goal

This file is the short-term progress guide for NuSelf. It narrows the next implementation phase so day-to-day work does not sprawl across the whole roadmap.

## Focus

Add memory stats and richer query commands.

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

## Scope

- Add `memory stats` for type, review state, candidate state, and temporal coverage.
- Add richer `memory search` filters for type, tag, review state, and temporal fields.
- Keep deterministic behavior without a live LLM.
- Keep output compact enough for CLI scanning.
- Keep repositories independently testable.

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
- Local source ingestion.

## Completion Criteria

- Stats command is covered by CLI tests.
- Filtered search behavior is covered by repository and CLI tests.
- README TODOs and planning docs reflect the completed query/stats slice before moving to the next goal.
