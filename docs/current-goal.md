# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — unify all authority-scoped Memory capabilities in `MemoryService`.

## Objective

Delete `MemoryWorkflowService` and `ChatCompletionService`; expose one Memory
service for entries, candidates, observations, recovery plans, curation, and
optimization while keeping Chat-to-Memory conversion as an application
projection adapter.

## Next Steps

1. Update Memory and module-boundary specifications for the single service.
2. Move workflow operations into `MemoryService` and compose its full
   authority dependencies once.
3. Delete both extra services and their `ApplicationGraph` fields.
4. Route CLI, REPL, and daemon consumers through `application.memory`.
5. Preserve safe post-chat observation projection and its degradation tests.
6. Run full validation and merge through a short-lived PR.

## Exclusions

- Moving repository implementations out of the Memory package.
- Moving Chat-to-Memory DTO conversion into the Memory domain.
- Unifying CLI synchronous curation with daemon scheduled curation.
- Redesigning curator or optimizer internals.

## Completion Evidence

- `ApplicationGraph` exposes only `memory: MemoryService` for Memory behavior.
- No production reference to either removed Service remains.
- All former workflow consumers use `MemoryService`.
- Post-chat observation failure remains secondary to committed replies.
- Full tests, Pyright, builds, and CI pass.
