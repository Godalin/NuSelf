# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Complete NuSelf's module decoupling and shared-infrastructure extraction so
the project has explicit dependency direction, centralized composition, and
stable boundaries for long-term development.

## Active Branch

Current working branch for v0.3.1.

## Ordered Work

1. Define and enforce package dependency rules. Complete: AST gates now reject
   runtime/domain/agent imports that point back to outer adapters.
2. Establish one runtime composition root shared by daemon and direct mode.
   Complete: CLI and daemon entrypoints borrow one lazy `ApplicationRuntime`
   and close it once at their outer lifecycle boundary.
3. Remove hidden backend/path resolution from domain repositories. Complete:
   trace, profile, reason, reflection, memory, source, notification, persona
   prompt, and curator-plan persistence require explicit authority resources
   and application-owned composition.
4. Extract narrow cross-domain ports and shared contracts.
5. Remove agent/domain dependencies on CLI/TUI presentation.
6. Split oversized cross-cutting modules along their actual ownership.
7. Run complete gates and close the goal with dependency evidence.

## Out Of Scope

- Changing the software version beyond v0.3.1.
- Release publication.
- New end-user features unrelated to architecture boundaries.

## Completion Evidence

In progress:

- authoritative module-boundary and shared-extraction rules are documented;
- AST dependency gates cover runtime, business domains, and agent adapters;
- agent trace tools no longer import terminal renderers and instead return
  model-facing structured JSON;
- `ApplicationRuntime` is now the sole explicit, idempotently closed owner for
  resolved paths, the selected authority backend, and its application graph;
  the superseded parallel authority-runtime abstraction was removed;
- CLI handlers reuse the invocation-scoped graph, while daemon state receives
  the process-owned runtime explicitly; normal, interrupt, startup-failure, and
  cleanup-failure paths converge on the same idempotent close operation;
- trace repositories and services no longer resolve a default backend;
  application-owned composition receives resolved paths and the selected
  authority backend explicitly, and an AST gate prevents the repository from
  restoring hidden backend or path lookup;
- profile persistence and aggregation now receive explicit resources and are
  assembled by the application layer; their domain package has the same
  authority-resolution gate as trace;
- reason persistence now receives explicit paths and storage and has its own
  application-owned constructor plus authority-resolution and inward
  dependency regression gates; the reason domain no longer imports application
  composition;
  cold application and CLI imports pass after removing the resulting
  reason-to-application cycle;
- reflection persistence now receives explicit paths and storage; reflection
  workflows no longer import outward application composition, and both
  invariants have executable regression gates;
- `ApplicationGraph` now owns one authority-scoped Memory/Reason/Reflection/
  Trace graph; memory candidates and sources reuse its entry/profile/candidate
  collaborators, memory/source repositories cannot restore authority lookup,
  and CLI memory adapters compose through the application boundary;
- notification persistence and per-entry lock paths now receive the graph's
  explicit paths/backend, with CLI, daemon, reflection, and delivery workflows
  sharing the injected outbox and an authority-resolution regression gate;
- persona prompts and memory curator recovery plans are now graph-owned
  persistence; their repositories receive explicit paths/backend or collection
  resources, and boundary gates cover the complete migrated persistence set;
- the first focused boundary gate passed 74 tests; infrastructure and storage
  regression coverage passed 307 tests; the trace integration slice passed
  600 tests after moving trace composition into the application layer; the
  profile integration slice passed 756 tests; the reason integration slice
  passed 966 tests including subprocess cold starts; the reflection integration
  slice passed 815 tests and cold imports; the memory/source cross-module slice
  passed 1280 tests, followed by the complete 2464-test suite; Pyright reported
  0 errors and 0 warnings. The notification cross-module slice passed 1117
  tests, followed by the complete 2465-test suite, with Pyright still at 0
  errors and 0 warnings. The persona/curator/CLI slice passed 908 tests and its
  focused persistence slice passed 56 tests; Pyright remained clean.
  The shared CLI/daemon runtime integration slice passed 533 tests, and its
  focused lifecycle slice passed 27 tests.
