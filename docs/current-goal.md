# Current Goal

This file is the short-term progress guide for NuSelf. It narrows the next implementation phase so day-to-day work does not sprawl across the whole roadmap.

## Focus

Add the memory candidate review queue.

## Status

Recently completed foundation slice:

- `MemoryEntry` now has a clear migration path into a `MemoryObject` envelope.
- `MemoryTypeRegistry` validates descriptor-backed memory objects.
- Core descriptors cover `belief`, `preference`, `episode`, and `instruction`.
- Existing file-backed memory entries remain inspectable and usable during migration.
- Curator and optimizer writes pass through repository-level descriptor validation.

## Scope

- Add file-backed candidate storage under ignored `private/`.
- Add CLI commands for candidate `list`, `show`, `accept`, `edit`, `merge`, and `reject`.
- Keep candidate records inspectable and review-state explicit.
- Route accepted or edited candidates through `MemoryEntryRepository` so descriptor validation still gates durable memory writes.
- Keep curator and optimizer direct writes working until they are migrated to propose candidates.

## Not Now

- Symbolic graph implementation.
- Plugin loading.
- Full decay and reflection rule execution.
- Vector or graph indexes.
- Proactive reflection and notification work.
- Web or GUI interface work.
- Replacing curator and optimizer direct writes with candidate-only workflows.

## Completion Criteria

- Candidate repository CRUD is covered by tests.
- CLI review commands are covered by tests.
- Accept, edit, and merge operations validate through the typed memory repository.
- README TODOs and planning docs reflect the completed review-queue slice before moving to the next goal.
