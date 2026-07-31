# Module Boundaries

Status: authoritative for v0.3.1.

## Purpose

NuSelf modules are separated by ownership and dependency direction, not merely
by directory names. Shared infrastructure exists only for semantics that are
genuinely common. A shared module must reduce coupling; it must not become a
generic dumping ground that every package can import.

## Dependency Direction

The stable direction is:

```text
CLI / daemon / agent-tool / TUI adapters
                    |
          application composition
                    |
       domain services and workflows
                    |
      repositories and declared ports
                    |
      runtime / storage / filesystem
```

The following import rules are mandatory:

- `nuself.runtime` is dependency-neutral infrastructure. It must not import
  CLI, daemon, agent, TUI, REPL, or business-domain packages.
- Storage, configuration, scope, clock, and private-filesystem foundations
  must not import presentation or process adapters.
- Business-domain packages must not import CLI, daemon, TUI, or REPL modules.
- `nuself.agent` may depend on domain services and framework APIs, but never on
  terminal presentation or daemon/CLI adapters.
- CLI, daemon, and TUI are outer adapters and may depend inward.
- A function-local import does not exempt a dependency from these rules.

These rules are checked from the Python AST in the test suite. New exceptions
require a specification change naming the owner and removal condition; an
unrecorded allowlist is forbidden.

## Composition Ownership

Scope and paths are resolved once by an outer composition root. Storage is
opened once for that authority. Domain repositories receive both the selected
`StorageBackend` and resolved `RuntimePaths` as explicit constructor
dependencies; accepting a project root and resolving either dependency inside
the repository is forbidden. Services receive repositories, clocks, sinks,
and cross-domain capabilities explicitly.

`ApplicationRuntime` is the shared authority-lifetime owner. Its public
factory resolves paths without opening storage; the first graph access selects
one backend and constructs the complete authority-scoped `ApplicationGraph`.
It is context-manageable, closes idempotently, and rejects graph access after
close. It is only created by an outer process adapter; domain code receives
the graph's narrow repositories and services rather than looking up the
runtime.

`get_default_backend()` and `runtime_paths()` are compatibility-free
composition helpers, not domain service locators. Domain repositories must not
call them. Direct CLI mode and daemon mode must construct the same service
graph; transport and lifecycle ownership are their only differences.

The trace package is the first migrated domain boundary. `TraceRepository`
requires an explicit `StorageBackend` and `RuntimePaths`, and `TraceRecorder`
and `TraceQueryService` require an explicit repository. `nuself.application`
owns the factory that assembles those concrete objects into immutable
`TraceServices`; the domain package does not own an authority-resolving
factory. Reintroducing backend or path resolution in the trace package is
forbidden and covered by executable architecture tests.

Profile follows the same boundary: `ProfileItemRepository` receives resolved
paths and storage, profile aggregation receives a repository, and the
application layer owns concrete profile construction. Neither domain may
recover authority resources from a project root.

`ReasonRepository` likewise receives resolved paths and storage, and the
application layer owns its concrete factory. Existing reason workflow
constructors remain migration scope and may still resolve authority while the
service graph is centralized, but the repository itself must never recover
authority. Reason domain modules must not import the application package:
doing so creates an application→reason→application cycle during cold process
startup.

`ReflectionRepository` follows the same persistence boundary: construction
requires resolved paths and the selected backend, while concrete assembly is
owned by the application layer. Reflection workflow constructors remain
migration scope until the shared service graph owns their complete lifecycle;
they may not move authority lookup back into the repository.

Memory persistence is composed as one authority-scoped graph.
`MemoryEntryRepository`, `MemoryCandidateRepository`, and `SourceRepository`
all require resolved paths and the selected backend. Candidate and source
repositories receive the concrete entry/profile/candidate collaborators they
mutate instead of constructing them during an operation. Aggregate functions
such as memory statistics receive repositories rather than resolving an
authority. The application layer owns the immutable repository bundle and
must reuse its instances for one authority.

Curator recovery plans are part of that memory persistence graph. Their store
receives the same resolved paths and selected backend so its durable records
and per-thread locks cannot drift across authorities. Persona prompt
persistence likewise receives its collection and resolved paths explicitly;
outer tools and adapters may compose those resources but the repository may
not select them.

`ApplicationGraph` is constructed from one already-resolved `RuntimePaths` and
one selected `StorageBackend`. It retains those exact resources and the shared
memory, notification, persona, reason, reflection, and trace graph. Process
adapters may choose transport and lifecycle, but must not rebuild domain
dependencies after a graph has been supplied.

Each CLI invocation and each daemon process owns exactly one
`ApplicationRuntime`. That runtime resolves the authority once, selects one
backend, constructs one `ApplicationGraph`, and closes the owned backend
idempotently at the outer lifecycle boundary. Command handlers and daemon
workers borrow the graph; they neither rebuild it nor close its resources.
Interrupt and exceptional exits follow the same outer cleanup path as normal
completion.

Daemon chat receives its memory, profile, reflection, trace, and thread-storage
collaborators from that graph. Nested chat/tool constructors may accept those
narrow collaborators, but must not resolve a backend or compose a second
repository graph after injection.
Direct and daemon chat use the same application-owned conversation factory.
Transport-specific job sinks, planners, and event publishers are parameters;
memory/profile/reflection/trace repositories and thread storage always come
from the supplied `ApplicationGraph`. Post-turn curation follows the same rule.

Daemon curation, reflection, reasoning, and notification workers follow the
same rule: process composition supplies their backend, repositories, outbox,
plans, and trace recorder from the existing graph. A worker must not select a
second authority after those collaborators have been supplied.

Reflection scheduling is orchestration, not a composition root. Candidate
generation, relevance evaluation, organization, schedule-state storage, and
publication dependencies are constructed outside the scheduler and injected.
Those collaborators may depend on reflection-owned repository interfaces, but
must not rediscover storage after explicit resources are provided.

`ApplicationRuntime` is the only public authority lifecycle abstraction.
Parallel path/backend owners with narrower names are prohibited because they
make teardown responsibility ambiguous.

`NotificationOutbox` is persistence and follows the same rule: it receives
resolved paths and the selected backend, derives its entry-lock directory only
from those paths, and never resolves authority itself. The application graph
owns the concrete outbox used by outer adapters and notification workflows.
Notification delivery orchestration is a separate module: it borrows an
outbox and a frozen adapter plan, but does not own storage selection or
per-entry locking. The package root may re-export these public types; it may
not contain both persistence and delivery-loop implementations.

Cross-domain behavior depends on a narrow `Protocol` owned by the consumer or
by a neutral contracts module. It must not depend on another domain's concrete
repository merely to call one capability.

Profile consumers use the stable `ProfileRepositoryPort` contract rather than
the concrete storage adapter. The contract exposes only list/search and the
mutations required by memory candidate workflows; authority paths, collections,
reindexing, and storage implementation remain private to profile composition.

Reflection promotion depends only on two consumer-owned capabilities:
`ReasonThreadStarter` and `ReflectionPromotionRecorder`. It must not require
the complete reason service or trace recorder contract merely to start one
thread and record one promotion.

## Shared Infrastructure Extraction

Code becomes shared infrastructure only when all of these are true:

1. at least two owners require the same semantics, not merely similar syntax;
2. one neutral owner can state the complete lifecycle and error contract;
3. consumers can depend inward without creating a cycle;
4. configuration and mutable state remain instance-scoped;
5. the extracted API is narrower than the implementations it replaces.

Shared contracts, immutable result types, validation, correlation context,
handler primitives, clocks, atomic persistence, and lifecycle cleanup are good
candidates. Domain policy, terminal wording, provider-specific behavior, and
one-off convenience wrappers remain with their owners.

Shared modules use specific names such as `runtime.handlers` or
`runtime.cleanup`; new catch-all `utils`, `helpers`, or `common` modules are
forbidden. Existing modules with those names must remain narrowly scoped.

## Presentation Boundary

Domain models expose typed state or wire-safe data. Agent tools return
model-facing structured text owned by the agent adapter. TUI and CLI renderers
own terminal color, layout, labels, and interactive formatting.

Agent tools and domain services must not reuse a TUI renderer merely because
both outputs are strings. If two adapters need identical neutral
serialization, that serializer belongs beside the domain contract and must not
import presentation infrastructure.

## Migration Order

Decoupling proceeds from enforceable boundaries inward:

1. reject adapter-direction violations;
2. centralize runtime composition;
3. inject storage and resolved paths into repositories;
4. replace concrete cross-domain dependencies with narrow ports;
5. split oversized cross-cutting modules after ownership is explicit.

Each step removes the old path repository-wide. NuSelf does not retain parallel
service locators, forwarding APIs, or deprecated construction paths during
active v0.3.1 development.
