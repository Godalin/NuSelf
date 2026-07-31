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
   In progress: process surfaces share application-owned chat and curator
   factories; remaining constructor fallbacks are being removed.
3. Remove hidden backend/path resolution from domain repositories. Complete.
4. Extract narrow cross-domain ports and shared contracts. In progress.
5. Remove agent/domain dependencies on CLI/TUI presentation. Complete.
6. Split oversized cross-cutting modules along actual ownership. In progress:
   notification delivery, reflection schedule state, candidate generation,
   and relevance evaluation are now separated; the remaining oversized-module
   audit is pending.
7. Run complete gates and close the goal with requirement-by-requirement
   dependency evidence.

## Out Of Scope

- Changing the software version beyond v0.3.1.
- Release publication.
- New end-user features unrelated to architecture boundaries.

## Current Evidence

- `ApplicationRuntime` is the sole process-level authority owner.
- CLI and daemon reuse application-owned conversation and curator factories.
- Reflection repositories, scheduling collaborators, notification outbox,
  persona prompts, memory/source/profile/reason/trace persistence, and agent
  tool services receive explicit resources at their migrated boundaries.
- AST gates enforce dependency direction, presentation isolation, authority
  lookup restrictions, and application-owned process composition.
- The combined composition phase passed 2473 locked tests; Pyright analyzed
  376 files with 0 errors and 0 warnings.
- Reflection schedule-state schema and strict decoding are being moved into
  `reflection.schedule_state`; its focused slice passed 129 tests and the
  complete suite passed 2474 tests with Pyright clean. Candidate/relevance
  module splitting remains.
- Model-backed relevance evaluation and candidate generation now live in
  `reflection.relevance` and `reflection.candidates`; the scheduler is reduced
  to lifecycle policy and publication orchestration, and cold CLI plus
  cross-process storage imports pass without a reflection/chat cycle. The
  focused split/cold-start slice passed 133 tests and the complete suite passed
  2476 tests with Pyright clean.

## Completion Standard

The goal remains active until the remaining hidden service composition and
oversized mixed-ownership modules are removed, all architecture gates cover
the resulting boundaries, full tests/type/build/wheel gates pass, and a final
audit proves every ordered item rather than merely finding no test failures.
