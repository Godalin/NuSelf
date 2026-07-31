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
   Complete: CLI and daemon entrypoints borrow one lazy `ApplicationRuntime`;
   direct/daemon chat, tools, curation, and background schedulers use
   application-owned factories over its graph.
3. Remove hidden backend/path resolution from domain repositories. Complete:
   trace, profile, reason, reflection, memory, source, notification, persona
   prompt, and curator-plan persistence require explicit authority resources
   and application-owned composition.
4. Extract narrow cross-domain ports and shared contracts. Complete: profile
   consumers and reflection promotion use narrow capabilities, while shared
   chat/worker factories inject concrete implementations only at application
   composition boundaries.
5. Remove agent/domain dependencies on CLI/TUI presentation. Complete: the
   dependency scan is clean and executable AST gates cover both domains and
   agent adapters.
6. Split oversized cross-cutting modules along their actual ownership.
   Complete: notification delivery is separated from persistence, and
   reflection persistence/composition moved outside scheduler orchestration;
   remaining colocated reflection policy types share one domain lifecycle and
   are not cross-cutting infrastructure.
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
- daemon chat now receives the graph-owned memory, profile, reflection, trace,
  and thread-storage collaborators; its tool runtime cannot rebuild reflection
  persistence from a project root;
- daemon memory curation, reflection scheduling, and reason scheduling now
  receive the same graph-owned backend, repositories, outbox, plans, and trace
  recorder instead of rebuilding those persistence collaborators;
- reflection scheduling, candidate generation, relevance evaluation, and
  organization now require explicit persistence collaborators; their only
  production composition lives in `nuself.application.reflection`, and an AST
  gate prevents scheduler/organizer authority lookup from returning;
- direct and daemon chat now share application-owned conversation and curator
  factories; reason, trace, persona, memory, reflection, and thread-storage
  tool collaborators are injected before the agent layer, with AST gates
  preventing tool composition from resolving authority;
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
- notification delivery orchestration is split from outbox persistence into
  its own module and operates only on an injected outbox and adapter plan;
- persona prompts and memory curator recovery plans are now graph-owned
  persistence; their repositories receive explicit paths/backend or collection
  resources, and boundary gates cover the complete migrated persistence set;
- the first shared cross-domain contract, `ProfileRepositoryPort`, limits
  memory consumers to profile list/search and required candidate mutations;
  an AST gate prevents core memory persistence from importing the concrete
  profile adapter;
- reflection promotion now depends only on `ReasonThreadStarter` and
  `ReflectionPromotionRecorder`, not the full cross-domain service contracts;
  domain and agent presentation boundaries remain clean under AST gates;
- notification delivery polling and frozen adapter-plan execution moved out of
  the persistence package root into `notification.delivery`; an AST gate keeps
  the delivery loop from returning to the outbox owner;
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
  focused persistence slice passed 56 tests; Pyright remained clean. The
  shared CLI/daemon runtime lifecycle slice passed 742 tests, followed by the
  complete 2467-test suite; Pyright again reported 0 errors and 0 warnings.
  The shared CLI/daemon runtime integration slice passed 533 tests, and its
  focused lifecycle slice passed 27 tests.
  The daemon-to-chat graph injection slice passed 156 tests; Pyright remained
  clean.
  The profile-port memory slice passed 232 tests with Pyright clean.
  The reflection-port and presentation-boundary slice passed 18 tests with
  Pyright clean.
  The notification delivery split passed 105 focused tests.
  The notification module-split slice passed 76 tests with Pyright clean.
  The daemon worker graph-injection slice passed 793 tests; Pyright reported
  0 errors and 0 warnings. The combined changes then passed the complete
  2470-test suite.
  The combined reflection/chat/persona/process-composition slice passed 1159
  tests; locked Pyright analyzed 376 files with 0 errors and 0 warnings. The
  complete suite then passed 2473 tests.
