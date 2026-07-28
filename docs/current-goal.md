# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Remove the process-global reason-output section planner and make its lifecycle
explicit through daemon-to-chat service composition.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Trace planner ownership from daemon startup through chat export tools.
2. [x] Specify instance-scoped planner composition and default behavior.
3. [x] Inject planner through chat runtime and tool construction.
4. [x] Remove global setter/state and add isolation tests.
5. [x] Audit remaining process-global runtime mutation.
6. [x] Run full tests, type checking, and formatting checks.
7. [ ] Commit and push together with the pending remote synchronization.

## Out Of Scope

- Changing section-planning prompts or the mechanical fallback algorithm.
- Introducing a general dependency-injection framework.
- Changing reason export tool or manifest contracts.

## Completion Evidence

- Two `ReasonOutputService` instances can use different planners concurrently.
- Constructing or starting one daemon does not change another runtime's planner.
- No runtime module setter or mutable global owns planner behavior.
- Existing no-planner callers retain deterministic mechanical planning.
- Full pytest, Pyright, and `git diff --check` pass.

## Next Review Batch

Move CLI/REPL history, completer, and display state from process-global module
variables into explicit session ownership, then consolidate daemon worker
start/stop/join state transitions behind one lifecycle primitive. Process-wide
lock registries and project-keyed caches remain infrastructure caches, not
runtime behavior callbacks.
