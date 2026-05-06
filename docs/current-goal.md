# Current Goal

This file is the short-term progress guide for NuSelf. It narrows the next implementation phase so day-to-day work does not sprawl across the whole roadmap.

## Focus

Build the typed memory pipeline foundation.

## Scope

- Add a `MemoryObject` envelope for long-term memory.
- Add a `MemoryTypeDescriptor` registry.
- Add built-in descriptors for `belief`, `preference`, `episode`, and `instruction`.
- Keep existing memory CLI workflows usable during the migration.
- Keep file-backed memory objects authoritative and inspectable.

## Not Now

- Symbolic graph implementation.
- Plugin loading.
- Full decay and reflection rule execution.
- Vector or graph indexes.
- Proactive reflection and notification work.
- Web or GUI interface work.

## Completion Criteria

- Current `MemoryEntry` behavior has a clear migration path into `MemoryObject`.
- Descriptor validation and summaries are covered by tests.
- Curator and optimizer can route proposed memory changes through descriptor validation.
- README TODOs and planning docs reflect the completed slice before moving to the next goal.
