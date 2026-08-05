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

1. Define and record the Service retention criteria.
2. Merge candidate review into `MemoryService` and remove its parallel graph
   field and module.
3. Remove duplicate Persona Service aliases and migrate callers.
4. Rename remaining compound Service modules where package context is enough.
5. Add architecture guards, run full verification, commit in stages, and
   return this file to Idle.

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
- Architecture tests, full pytest, Pyright, and `git diff --check` pass.
