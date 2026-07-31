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

1. Define and enforce package dependency rules. Complete.
2. Establish one runtime composition root shared by daemon and direct mode.
   Complete.
3. Remove hidden backend/path resolution from domain repositories. Complete.
4. Extract narrow cross-domain ports and shared contracts. Complete.
5. Remove agent/domain dependencies on CLI/TUI presentation. Complete.
6. Split oversized cross-cutting modules along actual ownership. Complete.
7. Run complete gates and close the goal with requirement-by-requirement
   dependency evidence. In progress.

## Out Of Scope

- Changing the software version beyond v0.3.1.
- Release publication.
- New end-user features unrelated to architecture boundaries.

## Current Evidence

- Application-owned persona, reason, chat, thread, reflection, curator,
  notification, trace, memory, workspace, and output-contract composition is
  committed through `e52425e`.
- Persona tools, reason advancers, schedulers, output services, conversation
  runtime, and thread storage no longer resolve storage authority.
- The committed reason-export phase passed 270 focused tests and Pyright with
  0 errors and 0 warnings.
- `PrivateWorkspaceStore` now receives `RuntimePaths`, and daemon export
  composition injects it before worker startup. Its focused workspace/export
  slice passed 80 tests and Pyright clean.
- Reason-output durable DTOs and strict codecs now live in
  `reason.output_contracts`; `reason.output` contains only workflow and its
  local rendering/planning helpers. The reason/daemon-export/agent/chat slice
  passed 639 tests and Pyright clean.
- The final source audit finds no authority lookup in agent, memory, persona,
  profile, reason, reflection, trace, or workspace modules; no domain imports
  of CLI/daemon/TUI/REPL; and no constructor-shaped `or Service(...)` fallback.
- Final local gates passed: 2494 tests; Pyright 0 errors/0 warnings; sdist and
  wheel build; clean Python 3.14 wheel install, critical imports, and
  `nuself --version` smoke.

## Completion Standard

The goal remains active until final hidden-composition and oversized-module
audits are complete, architecture gates cover the resulting boundaries, full
tests/type/build/clean-wheel gates pass on final code, commits are pushed, and
the final CI matrix is green.
