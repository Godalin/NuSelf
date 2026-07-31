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
3. Remove hidden backend/path resolution from domain repositories. In
   progress: trace, profile, reason, reflection, memory, and source persistence
   now require explicit authority resources and application-owned composition;
   notification persistence remains.
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
- `AuthorityRuntime` now provides one explicit, idempotently closed owner for
  resolved paths and a closeable authority backend; process adapters can share
  this primitive without turning it into a domain service locator;
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
- the first focused boundary gate passed 74 tests; infrastructure and storage
  regression coverage passed 307 tests; the trace integration slice passed
  600 tests after moving trace composition into the application layer; the
  profile integration slice passed 756 tests; the reason integration slice
  passed 966 tests including subprocess cold starts; the reflection integration
  slice passed 815 tests and cold imports; the memory/source cross-module slice
  passed 1280 tests; Pyright reported 0 errors and 0 warnings.
