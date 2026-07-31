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
- Memory intake now requires an explicit profile port; CLI composition supplies
  the graph-owned profile repository and the agent cannot resolve authority.
- Reflection promotion service now requires repository, reason-thread starter,
  and promotion recorder ports; CLI/REPL compose them from the application
  graph instead of letting the domain service open storage.
- Memory optimization now requires explicit paths and graph-owned entry,
  candidate, and profile repositories; CLI maintenance uses application
  composition for both curator and optimizer.
- Reason services used by process surfaces now come from one application
  factory shared by CLI, REPL, chat, reflection, and daemon scheduling.
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
- `ReflectionService` now accepts only required repository, reason-start, and
  promotion-recording ports; application composition owns its concrete graph
  and CLI/REPL reuse the invocation-scoped authority.
- CLI, REPL, chat, reflection, and daemon reason operations now use
  `application.reason.compose_reason_service`; MemoryOptimizer also requires
  graph-owned entry, candidate, and profile repositories.
- `ReasonService` now requires repository, workspace, and trace dependencies;
  ReasonScheduler, ReasonOutputService, and the daemon export worker receive an
  existing service instead of constructing a fallback service graph.
- `MemoryCurator` now requires paths, backend, thread store, repositories,
  recovery-plan store, and trace recorder; only application composition creates
  its concrete authority graph.
- Curator settings, structured actions, durable cursor schema, and result DTO
  now live in `memory.curator_contract`, separate from workflow orchestration.
- `ConversationGraphRuntime` no longer resolves paths, storage, repositories,
  reason, trace, or persona dependencies; application composition supplies the
  complete production runtime and tests use an explicit fixture composition.
- `ConversationGraphRuntime` now requires its complete memory, thread,
  reflection, reason, trace, and persona capability set; `application.chat`
  is the sole production and evaluation composition boundary.

## Completion Standard

The goal remains active until the remaining hidden service composition and
oversized mixed-ownership modules are removed, all architecture gates cover
the resulting boundaries, full tests/type/build/wheel gates pass, and a final
audit proves every ordered item rather than merely finding no test failures.
