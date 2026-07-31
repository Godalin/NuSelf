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
3. Remove hidden backend/path resolution from domain repositories.
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
- the first focused boundary gate passed 74 tests and Pyright reported
  0 errors and 0 warnings.
