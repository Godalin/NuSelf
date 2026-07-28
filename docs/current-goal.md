# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Consolidate daemon background-worker start, stop, join, liveness, and cleanup
state behind one typed lifecycle primitive.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Inventory worker-specific lifecycle behavior and asymmetries.
2. [x] Specify lifecycle states, duplicate start, shutdown, and timeout rules.
3. [x] Implement a reusable owned-worker primitive with focused tests.
4. [x] Migrate daemon workers without changing scheduling semantics.
5. [x] Make health snapshots consume the unified lifecycle state.
6. [x] Run full tests, type checking, and formatting checks.
7. [x] Commit this stage as one functional change.

## Out Of Scope

- Unifying each worker's interval, queue, retry, or domain operation.
- Replacing threads with asyncio or external process supervision.
- Changing daemon commands or health response fields.

## Completion Evidence

- Duplicate start cannot create two worker threads.
- Stop/join state is explicit and join timeout remains observable.
- All daemon worker health snapshots derive liveness consistently.
- Export timers retain their specialized cancellation cleanup.
- Focused lifecycle tests, full pytest, Pyright, and `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Classify remaining broad exception handlers and silent fallbacks. Migrate
unjustified suppression to propagation, observable best effort, or explicit
corrupt-record isolation without changing intentional compatibility behavior.
