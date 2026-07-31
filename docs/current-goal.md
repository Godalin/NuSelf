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
   In progress: the final workspace path-resolution fallback is being removed.
3. Remove hidden backend/path resolution from domain repositories. Complete.
4. Extract narrow cross-domain ports and shared contracts. In progress.
5. Remove agent/domain dependencies on CLI/TUI presentation. Complete.
6. Split oversized cross-cutting modules along actual ownership. In progress;
   the final audit found reason-output durable contracts mixed with export
   workflow; those contracts now live in `reason.output_contracts`.
7. Run complete gates and close the goal with requirement-by-requirement
   dependency evidence.

## Out Of Scope

- Changing the software version beyond v0.3.1.
- Release publication.
- New end-user features unrelated to architecture boundaries.

## Current Evidence

- Application-owned persona, reason, chat, thread, reflection, curator,
  notification, trace, and memory composition is committed through `8d97935`.
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

## Completion Standard

The goal remains active until final hidden-composition and oversized-module
audits are complete, architecture gates cover the resulting boundaries, full
tests/type/build/clean-wheel gates pass on final code, commits are pushed, and
the final CI matrix is green.
