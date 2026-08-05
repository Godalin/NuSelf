# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — auditing and normalizing Service boundaries.

## Objective

Merge same-domain forwarding Services into their domain Service, retain
Services that enforce a real domain/capability/workflow boundary, and normalize
the affected modules to single-word filenames.

## Next Steps

1. Completed: defined and recorded the Service retention criteria.
2. Completed: merged candidate review into `MemoryService` and removed its
   parallel graph field and module.
3. Completed: removed duplicate Persona Service aliases and migrated callers.
4. Completed: renamed affected compound Service modules.
5. In progress: commit the verified implementation and return this file to
   Idle.

## Exclusions

- Do not merge Services across independent domain packages merely because an
  implementation currently delegates to one Repository.
- Do not merge capability projections that enforce narrower access, such as
  bounded conversation history or Trace query/recording separation.
- Do not merge workflow/job Services that own orchestration, durable state,
  retries, recovery, or external adapters.

## Completion Evidence

- `MemoryService` owns candidate review; `MemoryCandidateService`, its graph
  field, and `candidate_service.py` no longer exist.
- Persona exposes one non-duplicated method vocabulary.
- Retained secondary Services have an explicit capability or workflow reason.
- Affected compound Service modules use single-word filenames.
- The closed API audit document is removed; governing conclusions live in the
  specification and executable tests.
- Architecture guards cover graph ownership and Service module filenames.
- `uv run --locked pytest`: 2,337 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- `git diff --check`: passed.
