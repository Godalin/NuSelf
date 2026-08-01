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
- The `nuself.runtime` package root is an import-light namespace. Consumers
  import `messages`, `context`, `events`, `jobs`, or the other owning module;
  the root must not eagerly aggregate independent runtime facilities.
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
Authority-scoped workspace storage follows the same rule: it receives resolved
`RuntimePaths`. Daemon workers borrow that store from process composition and
must not create it lazily during worker startup.

`ApplicationRuntime` is the shared authority-lifetime owner. Its public
factory resolves paths without opening storage; the first graph access selects
one backend and constructs the complete authority-scoped `ApplicationGraph`.
First access and close are serialized by one non-reentrant lifecycle lock;
runtime composition must not recursively request its own graph.
It is context-manageable, closes idempotently, and rejects graph access after
close. It is only created by an outer process adapter; domain code receives
the graph's narrow repositories and services rather than looking up the
runtime.
The runtime stores the lazily selected closable backend, its composed graph,
and closed lifecycle state. The backend is selected once under the existing
lifecycle lock and closed exactly once by the runtime; it is not borrowed from
or mirrored into the process-global default-backend cache. Process adapters may
borrow it only for explicit storage administration, never through the graph or
from domain code.

`auto_backend()` and `runtime_paths()` are composition helpers, not domain
service locators. Domain repositories must not call them. Direct CLI mode and
daemon mode construct the same service graph; transport and lifecycle ownership
are their only differences.

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
and per-conversation locks cannot drift across authorities. Persona prompt
persistence likewise receives its collection and resolved paths explicitly;
outer tools and adapters may compose those resources but the repository may
not select them.
Memory-backed persona definition loading receives the graph-owned memory
repository. Chat orchestration receives the resulting immutable definitions;
neither layer may resolve storage from a project root.
Persona agent tools receive their global prompt repository and trace recorder
as required capabilities. Reason-scoped persona tools additionally receive
resolved runtime paths for their workspace-local repository. Tool factories
may construct model adapters, but they must not call `runtime_paths()`, open a
backend, or compose trace services. The application reason factory supplies
the same graph-owned prompt and trace capabilities to every reason advancer.

`ApplicationGraph` is constructed from one already-resolved `RuntimePaths` and
one selected `StorageBackend`. It retains those exact resources and the shared
conversation, memory, notification, persona, reason, reflection, and trace
graph. Process
adapters may choose transport and lifecycle, but must not rebuild domain
dependencies after a graph has been supplied.

Each CLI invocation and each daemon process owns exactly one
`ApplicationRuntime`. That runtime resolves the authority once, selects one
backend, loads one immutable configuration snapshot, constructs one
`ApplicationGraph`, and closes the owned backend
idempotently at the outer lifecycle boundary. Command handlers and daemon
workers borrow the graph; they neither rebuild it nor close its resources.
Interrupt and exceptional exits follow the same outer cleanup path as normal
completion.
Application-owned Chat, daemon, notification, and model composition reuse that
snapshot. Explicit configuration inspection and adapters documented to reload
per operation may still call the loader; nested composition must not reload the
same snapshot merely to obtain one subsection.
One daemon startup resolves and orders its configured LLM endpoints once.
Chat, reflection, reasoning, persona discussion, and export receive that tuple
while retaining separate component-tagged agent wrappers; endpoint reuse does
not imply shared conversation state or a process-global model registry.
`nuself.agent.tools` package initialization imports no domain tool modules.
Chat-only aggregation lives in `agent.tools.composition`; domain code imports
its concrete tool module directly so importing decorators or one tool cannot
initialize Reason, Reflection, Memory, and Persona transitively.
`nuself.agent.chat` is likewise an import-light namespace. Application
composition imports its runtime, settings, result DTOs, response service, and
resource snapshots from their owning modules; the package root must not expose
conversation storage or initialize the complete Chat graph on import.
Domain package roots follow the same import-light rule when no cohesive public
facade is consumed by production code. The Reason, Persona, Reflection, Trace,
and Profile package roots are namespaces rather than aggregators: internal
consumers import the owning domain module directly. Importing these package
roots must not initialize model adapters, repositories, services, persistence,
workspace storage, graph orchestration, discussion, scheduling, or organization
as a side effect.

Daemon chat receives its memory, profile, reflection, trace, and conversation
collaborators from that graph. `application.chat` resolves them once into an
immutable `ConversationResources` snapshot, with a nested `ToolResources`
snapshot for the narrower tool boundary. Neither owns lifecycle, dispatch,
storage selection, or business behavior; they prevent the same resources from
being forwarded independently through every nested constructor. Conversation
and tool runtimes borrow only their respective snapshot and must not resolve a
backend or compose a second repository graph.
The tool snapshot exposes one `MemoryService`, not the entry repository beside
a query helper. Search, context packing, count, archive, and importance updates
are service use cases so tool code cannot bypass domain validation or acquire unrelated
memory mutations. Curator, source ingestion, projection, repair, and migration
remain domain/infrastructure workflows and may receive the repositories they
actually coordinate; they are not routed through a universal memory facade.
Direct and daemon chat use the same application-owned conversation factory.
Transport-specific job sinks, planners, and event publishers are parameters;
memory/profile/reflection/trace repositories and conversation storage always come
from the supplied `ApplicationGraph`. Post-turn curation follows the same rule.
Conversation state and persistence are isolated domain infrastructure under
`nuself.conversation`, not shared knowledge infrastructure. `ConversationStore`
receives resolved runtime paths and the selected backend as required resources
and is constructed exactly once in `ApplicationGraph`; only the conversation
API implementation, chat, and explicit conversation-management surfaces may
borrow it. Memory, reflection, reason, persona, notification, and trace code
must not import or query conversation state or storage. A domain that needs
chat evidence uses the read-only conversation history API and receives bounded,
immutable DTOs; this explicit API dependency is allowed.

A completed turn may cross into the knowledge system only through an
application-owned projector. The projector converts the committed turn into a
memory-owned durable observation containing an opaque source reference,
ordered text fragments, and trace correlation. Once accepted, the observation
is governed entirely by memory storage, locking, recovery, and retention.
Memory must not reconstruct an observation by opening conversation storage,
and daemon recovery must enumerate the memory inbox rather than conversations.
This establishes the dependency direction `conversation -> application event
projection -> memory`; there is no reverse edge.

Reflection candidate generation consumes durable memory entries, profile
items, imported sources, and optionally bounded excerpts supplied through the
read-only conversation API. It must not accept a `ConversationStore` or decode
conversation records. Conversation may consume reflection through user-facing
tools; the two directions meet only at their public APIs.

Daemon curation, reflection, reasoning, and notification workers follow the
same rule: process composition supplies their backend, repositories, outbox,
plans, and trace recorder from the existing graph. A worker must not select a
second authority after those collaborators have been supplied.

Reflection scheduling is orchestration, not a composition root. Candidate
generation, relevance evaluation, organization, schedule-state storage, and
publication dependencies are constructed outside the scheduler and injected.
Those collaborators may depend on reflection-owned repository interfaces, but
must not rediscover storage after explicit resources are provided.
The persisted schedule schema and strict codec belong to
`reflection.schedule_state`; orchestration imports that contract and does not
define storage records inline.
Model-backed relevance evaluation belongs to `reflection.relevance`.
Scheduling receives the gate as a collaborator and must not own its structured
output schema, prompt construction, failure policy, or cooldown-state decode.
Reflection user-intent operations receive repository, reason-start, and
promotion-recording ports as required constructor dependencies. They must not
resolve authority or construct concrete reason and trace services.
Proactive context collection and candidate generation belong to
`reflection.candidates`. Conversation history is supplied through the
read-only `ConversationHistoryReader` contract; the reflection domain must not
import the concrete store, chat runtime, or agent package.

`ApplicationRuntime` is the only public authority lifecycle abstraction.
Parallel path/backend owners with narrower names are prohibited because they
make teardown responsibility ambiguous.
Outer adapters use its context boundary directly rather than publishing
adapter-named pass-through aliases. Adapter composition helpers remain only
when they enforce adapter-specific authority or capability rules.
`ApplicationGraph` is a composition result, not a service locator. Process
adapters may borrow domain-facing capabilities from it, but raw
`StorageBackend`, `StorageCollection`, and repository construction remain
inside application composition, storage administration, and migrations.
Stable authority-scoped query and user-intent services are composed once in
the graph alongside their repositories. Chat, daemon, CLI, and cross-domain
services borrow those instances rather than reconstructing services and their
internal caches. One-operation strategies such as a model-backed reason
advancer are method inputs, not a reason to create a parallel service graph.
Initialized CLI and REPL commands always run inside one `ApplicationRuntime`;
helper functions must not create a fallback graph when that scope is absent.
The daemon server likewise owns its `ApplicationRuntime` and injects the
already-composed `ApplicationGraph` into request/task state. `DaemonState`
must not inspect a context variable, construct a fallback runtime, or retain
the lifecycle owner after composition.

The `nuself.application` package root is an import-light namespace. Process
adapters import each composition function or immutable resource bundle from
its owning application module; the root does not grow a second catalog of the
composition graph. By contrast, `nuself.decorators` is the deliberate public
spelling for the cohesive inert feature-declaration DSL and may re-export the
policies and decorators owned by `runtime.features`.

The `nuself.notification` package root is also import-light. Immutable records
and strict codecs belong to `notification.model`; storage and entry locking
belong to `notification.outbox`; adapter contracts and delivery orchestration
belong to `notification.adapters` and `notification.delivery`; concrete
adapters and their composition remain separate. These modules import one
another only in that direction, and the package root must not recreate their
former circular facade. Renderers and concrete adapters that only inspect an
entry depend on the model, not on storage and filesystem locking.

Cross-domain APIs stay coarse enough to represent a use case. Do not wrap
every repository method in a one-method interface, introduce a generic service
bus, or preserve parallel concrete and facade paths. A consumer-owned Protocol
is required only where one domain invokes another domain's capability.

`ConversationGraphRuntime` is an agent orchestration consumer, not a
composition root. Memory query/repository, conversation storage, reflection, reason,
trace, and persona-tool capabilities are mandatory inputs. Production and
evaluation surfaces obtain the concrete graph from `application.chat`.
The model/tool loop remains the framework-native LangChain `create_agent`
graph. NuSelf's fixed context, response, and state-update stages form one
direct typed pipeline; compression is follow-up work after commit. Wrapping
that branch-free sequence in a second
`StateGraph` is prohibited because it adds no checkpoint, routing, interrupt,
or recovery boundary.
Persona definitions are loaded from an explicitly supplied memory repository
at that application boundary and passed into chat persona orchestration;
persona policy must not resolve the active authority itself.

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
and storage implementation remain private to profile composition.
Memory intake receives that port explicitly; it is classification policy and
must not open storage when a caller omits profile context.
Memory optimization likewise receives resolved paths plus entry, candidate,
and profile repositories. CLI composition supplies the authority-scoped graph;
the optimizer never selects storage.

Reason operations used by CLI, REPL, chat, reflection, and daemon tasks are
composed once in `ApplicationGraph`. Process adapters reuse its reason service
instead of instantiating a root-based service independently.
Memory optimization likewise receives paths, entry/candidate repositories, and
the profile port explicitly; CLI and daemon composition must reuse the active
application graph rather than create a second authority graph.
Memory curation receives the complete authority resource set explicitly:
runtime paths, backend, observation inbox, entry/candidate/profile repositories,
recovery-plan store, and trace recorder. Defaults are limited to curation
policy and model adapters, never persistence or authority selection.
The required trace recorder remains non-null for the curator's complete
lifetime; curation isolates recorder failures through the memory observability
policy rather than retaining an unreachable no-recorder branch.
Daemon request handling may only request curation for a durable observation.
The unified daemon scheduler owns execution, retry isolation, and periodic
recovery across pending observation IDs; request handlers must not invoke the curator
model loop synchronously.
Its structured model contract, observation/plan wire formats, settings, and result DTO
belong to `memory.curator_contract`; `memory.curator` owns only workflow
orchestration and may re-export nothing merely for legacy import convenience.
Reason-output section, chunk, manifest, progress, path, and planner contracts
belong to `reason.output_contracts`, including their strict wire codecs.
`reason.output` owns export planning, persistence, composition, and rendering
workflow and imports those contracts; it must not define the durable schemas
inline.

Reason operations are composed once in `ApplicationGraph`. Process surfaces
reuse `reason_service` so repository, workspace, and trace dependencies
originate at one application boundary; an optional model-backed advancer is a
single-operation dependency rather than a second service graph.
`ReasonRepository` owns persistence and decode diagnostics; it does not expose
runtime paths so callers can reconstruct application composition from a
repository instance.
`ReasonService` itself receives repository, workspace store, and trace recorder
as required dependencies for its own thread lifecycle, but it does not expose
generic workspace paths or key-value handles as reason operations. Consumers
that need workspace infrastructure receive the single application-owned store
explicitly. The service stores that required recorder as a non-null capability;
trace failure isolation must not be modeled as optional composition. Reason
scheduling and output export must receive an existing reason
service and that workspace store.
Chat tools, model-backed advancement, service operations, and output export
reuse that store instead of constructing equivalent authority-scoped adapters.
Cooldown mutation is a reason
service use case; scheduling must not receive or expose the repository merely
to persist it. Daemon workers may own queues and workspace adapters, but must
not create or infer a second reason persistence graph. Agent reason tools
receive the export workspace capability from chat composition and never resolve
runtime paths to construct it.
`ReasonAdvancer` receives workspace, persona repository, trace recorder, and
resolved paths from application composition. `ReasonScheduler` receives an
advancer explicitly and never constructs one from a project root.

Reflection promotion depends only on two consumer-owned capabilities:
`ReasonThreadStarter` and `ReflectionPromotionRecorder`. It must not require
the complete reason service or trace recorder contract merely to start one
thread and record one promotion.
The reflection repository and both capabilities are mandatory constructor
dependencies. `ReflectionService` owns user-facing list, show, status-change,
organization, and promotion use cases; CLI, REPL, agent tools, and background
scheduling obtain that complete service from application composition rather
than accessing the repository or rebuilding the organizer. Reflection-owned
candidate and relevance workflows may still receive their repository
explicitly.

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

Logging persistence remains the single internal event-log implementation, but
its terminal warning schemas belong to `runtime.log_warning_contracts`. The
log engine consumes the sealed registry instead of defining presentation
warning validation beside append, rotation, recovery, and read semantics.

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
