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
- The `nuself.runtime` package root and its capability-package roots are
  import-light namespaces. Consumers import precise owners such as
  `runtime.audit.catalog`, `runtime.event.publisher`, or
  `runtime.job.message`; package roots must not eagerly aggregate independent
  facilities.
- Storage, configuration, scope, clock, and private-filesystem foundations
  must not import presentation or process adapters.
- Business-domain packages must not import CLI, daemon, TUI, or REPL modules.
- `nuself.agent` may depend on domain services and framework APIs, but never on
  terminal presentation or daemon/CLI adapters.
- CLI, daemon, and TUI are outer adapters and may depend inward.
- A function-local import does not exempt a dependency from these rules.

Concrete domain models belong to their owning packages. A horizontal `domain`
package is forbidden because it splits Memory, Profile, Source, or Reflection
semantics from their repositories and services without creating a reusable
infrastructure boundary.
Within an owning package, the primary persisted domain types live in
`model.py`, the main user-intent API in `service.py`, persistence in
`repository.py` or an accurate domain-specific owner, and multi-dependency
construction in `composition.py`. A role file exists only when the role is
real; empty template modules and pass-through compatibility modules are
forbidden. Directories provide context so responsibility filenames remain a
single word where practical.

Conversation is a first-class domain package. Its persisted types belong to
`conversation.model`, mutation and locking to `conversation.store`, and its
bounded cross-domain read API to `conversation.history`. The package root may
explicitly re-export that established public API, but no top-level
`conversation.py` compatibility module remains.

These rules are checked from the Python AST in the test suite. New exceptions
require a specification change naming the owner and removal condition; an
unrecorded allowlist is forbidden.

## Domain API Design Contract

NuSelf has one shared domain API design style, not one common `Service` base
class. Each role has a distinct contract:

| Role | Owns | Must not own |
| --- | --- | --- |
| Model | typed domain state and invariants | storage, rendering, runtime lookup |
| Service | complete user-intent operations and policy | CLI arguments, backend lifecycle, terminal output |
| Consumer port | the smallest cross-domain capability a consumer needs | unrelated methods from the concrete provider |
| Repository | domain persistence, codecs, and indexes | cross-domain orchestration or presentation |
| Composition | construction from already-resolved capabilities | authority reselection or business behavior |
| Adapter | transport, arguments, and presentation | domain decisions or direct raw-storage mutation |

Every domain service follows these rules:

1. Construction receives every repository, clock, sink, strategy, and
   cross-domain capability explicitly. It never reads the active application,
   resolves scope, or opens storage.
2. Public methods name domain use cases with verbs such as `start_thread`,
   `archive`, or `promote_to_reason`; they do not expose generic
   `execute(action)` or mirror CLI subcommands.
3. Inputs and results are domain models or typed value objects. `argparse`
   namespaces, daemon payloads, wire dictionaries, and rendered strings stop
   at their adapters or codecs.
4. Validation, state transitions, and required audit/trace behavior belong to
   the service. Domain-specific failures use stable domain exceptions; an
   adapter decides only how to transport or present them.
5. A cross-domain consumer depends on a structural `Protocol` that contains
   only the operations it uses. The provider may satisfy several ports without
   inheriting a common framework interface.
6. Repositories remain valid domain-internal capabilities for persistence,
   migrations, recovery, and explicit maintenance. A service method is added
   for a stable business use case, not merely to forward every repository
   method.
7. A service owns no `start`, `stop`, `health`, name registry, or backend close
   method unless that lifecycle is itself genuine domain behavior. Process and
   authority lifetime belong to outer composition.

Agent tools and daemon tasks are adapters over this contract. Feature
decorators describe tool identity, effects, confirmation, observation, and
audit without changing the callable's domain API. `DaemonTask` describes
scheduling and payload transport without becoming a domain service interface.
No `BaseService`, dynamic API registry, or service locator may be introduced to
simulate uniformity.

## Composition Ownership

Scope and paths are resolved once by an outer composition root. Storage is
opened once for that authority. Domain repositories receive both the selected
`StorageBackend` and resolved `RuntimePaths` as explicit constructor
dependencies; accepting a project root and resolving either dependency inside
the repository is forbidden. Services receive repositories, clocks, sinks,
and cross-domain capabilities explicitly.
`compose_application()` loads configuration from the `NuSelfScope` already
carried by those paths; it must not discard workspace/user-layer metadata and
reconstruct scope from the authority root.
Authority-scoped workspace storage follows the same rule: it receives resolved
`RuntimePaths`. Daemon workers borrow that store from process composition and
must not create it lazily during worker startup. The low-level workspace store
accepts only the resolved database path; it must not offer a convenience
constructor that resolves project or authority scope again.

`ApplicationRuntime` is the shared authority-lifetime owner. Its public
factory accepts the already-resolved `NuSelfScope` (or a path-only internal
authority when no scope metadata exists) and resolves paths without opening
storage. CLI composition passes its resolved scope rather than discarding it to
the root path. The first graph access selects one backend and constructs the
complete authority-scoped `ApplicationGraph`.
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

`TraceRepository` requires an explicit `StorageBackend` and `RuntimePaths`, and
`TraceRecorder` and `TraceQueryService` require an explicit repository. Trace
owns the factory that assembles those supplied resources into immutable
`TraceServices`; domain-owned composition must not resolve authority or open
storage. Reintroducing backend or path resolution in Trace composition is
forbidden and covered by executable architecture tests.

Profile follows the same boundary: `ProfileItemRepository` receives resolved
paths and storage, and profile aggregation receives a repository. Concrete
Memory composition supplies Profile's already-resolved resources; neither
domain may recover authority resources from a project root.

`ReasonRepository` likewise receives resolved paths and storage. Reason owns
its concrete workflow composition and accepts the graph capabilities needed by
each factory explicitly. Its repository and composition must never recover
authority. Type-only knowledge of `ApplicationGraph` is permitted only in
domain composition modules; Reason runtime and service modules must not import
the application package.

`ReflectionRepository` follows the same persistence boundary: construction
requires resolved paths and the selected backend, while concrete assembly is
owned by Reflection composition. The application root supplies explicit graph
capabilities and retains lifecycle ownership; Reflection may not move authority
lookup back into its repository or workflow constructors.
Reflection entry creation and replacement share the repository's single
stable-ID `save(entry)` operation; identical `add` and `update` aliases are not
separate capabilities. User status operations remain explicit on
`ReflectionService`, and organizer-owned duplicate archival remains in
`ReflectionOrganizer`; both persist the resulting entry through `save()`.
The repository does not re-resolve an entry merely to choose a domain status.
The repository owns both reflection-entry persistence and typed access to the
single reflection schedule record. Its schedule collection remains private:
`ApplicationGraph`, the scheduler, and the relevance gate must not receive or
mutate a raw `StorageCollection`. Scheduling policy and corruption reporting
remain in the scheduler/gate; the repository only decodes and saves the typed
state.

Concrete workflows belong to their domains even when an outer adapter triggers
them. Reason owns durable output export in `reason.export_service`; daemon owns
only scheduling and lifecycle. Notification owns its evaluation entry point in
`notification.eval`; CLI owns only argument handling and result presentation.
Generic execution infrastructure remains in `runtime`, while concrete owners
use responsibility names such as `application.lifecycle`, `agent.chat.engine`,
and `cli.repl.loop`.

Memory persistence is composed as one authority-scoped graph.
`MemoryEntryRepository`, `MemoryCandidateRepository`, and `SourceRepository`
all require resolved paths and the selected backend. Candidate and source
repositories receive the concrete entry/profile/candidate collaborators they
mutate instead of constructing them during an operation. Aggregate functions
such as memory statistics receive repositories rather than resolving an
authority. The application layer owns the immutable repository bundle and
must reuse its instances for one authority.
`MemoryEntryRepository.compute_graph()` is the single one-shot symbolic graph
projection used by both repository operations and external memory-query
expansion. A private mirror with identical behavior is not a second capability.
The public `list_relations()` operation likewise owns its one-shot relation
projection and filtering; a single-use private projection is not a separate
repository capability.
Memory entry persistence accepts the canonical `MemoryEntry` domain object;
an unused validate-convert-save adapter for `MemoryObject` is not repository
API. Legacy object-shaped records remain a decoding concern.
Source ingestion is the public document/chunk write operation. Replacing one
document's chunks is an internal ingestion step, not an independently exposed
repository capability that callers may separate from document persistence.
Writing the document record is likewise internal to ingestion; callers provide
a source path rather than assembling a partial stored document without its
chunks.

Memory-owned composition builds the concrete production registry graph from
supplied paths and storage.
Custom memory type and relation registries remain repository-construction
concerns for focused domain tests, not unused variability in the application
composition API.

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
completion. Graph construction and explicit infrastructure borrowing share one
lock-owned lazy backend acquisition path; closing also releases the runtime's
graph reference after admission is closed.
Domain-owned Chat, daemon, notification, and model composition reuse that
application snapshot. Explicit configuration inspection and adapters documented to reload
per operation may still call the loader; nested composition must not reload the
same snapshot merely to obtain one subsection.
One daemon startup resolves and orders its configured LLM endpoints once.
Chat, reflection, reasoning, persona discussion, and export receive that tuple
while retaining separate component-tagged agent wrappers; endpoint reuse does
not imply shared conversation state or a process-global model registry.
Structured-agent factories consume the supplied endpoint tuple and do not load
configuration from a project path. Omitted endpoints mean an explicit empty
set and produce the normal typed model-unavailable outcome on invocation.
`nuself.agent.tools` package initialization imports no domain tool modules.
Chat-only aggregation lives in `agent.tools.composition`; domain code imports
its concrete tool module directly so importing decorators or one tool cannot
initialize Reason, Reflection, Memory, and Persona transitively.
`nuself.agent.chat` is likewise an import-light namespace. Its concrete
composition module imports the engine, settings, result DTOs, response service,
and resource snapshots from their owning modules; the package root must not
expose conversation storage or initialize the complete Chat graph on import.
Domain package roots follow the same import-light rule when no cohesive public
facade is consumed by production code. The Reason, Persona, Reflection, Trace,
and Profile package roots are namespaces rather than aggregators: internal
consumers import the owning domain module directly. Importing these package
roots must not initialize model adapters, repositories, services, persistence,
workspace storage, graph orchestration, discussion, scheduling, or organization
as a side effect.

Daemon chat receives its memory, profile, reflection, trace, and conversation
collaborators from that graph. `agent.chat.composition` resolves them once into
an immutable `ConversationResources` snapshot, with a nested `ToolResources`
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
Conversation load and archive operations own their direct decode and immutable
state replacement; single-call forwarding helpers do not form additional API
boundaries.

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
Notification adapter composition likewise receives the graph's resolved
configuration explicitly; it must not reload configuration as an optional
fallback for CLI, REPL, or daemon callers.
Concrete adapters receive their resolved project path and subsystem config from
that composition boundary; they do not resolve authority or system config.

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
Application composition may select authority and lifecycle, but must not spell
out a domain's internal repository, organizer, or service construction. Those
details belong to the existing domain composition module. A process root may
explicitly connect finished public components when the construction occurs in
only one place; moving unique wiring behind another factory is not
simplification. Neither case justifies a facade, provider registry, or plugin
mechanism. Adapter-local helpers that merely discard arguments and return one
`ApplicationGraph` field are forbidden; adapters borrow that field directly.
Resource snapshots remain valid when they preserve shared repository identity
or form a real consumer-specific capability boundary.
When one domain exposes multiple authority-scoped capabilities that must share
internal identity, `ApplicationGraph` exposes one immutable domain-owned
resource snapshot rather than parallel flat fields. The snapshot contains
concrete capabilities but performs no lookup, dispatch, forwarding, or
lifecycle work. Reason groups its service and workspace; Reflection groups its
repository and service. Callers name the capability explicitly through that
domain resource and no flat compatibility aliases are retained.

Shared runtime files require either multiple consumers or an independently
testable protocol, codec, policy, or schema boundary. A helper used by exactly
one runtime owner and expressing only that owner's local validation belongs in
the owner module. Short daemon handlers remain valid when they adapt the
uniform `DaemonTask` signature, validate payloads, or mark a scheduler task
boundary; line count alone does not make them redundant.
Initialized CLI and REPL commands always run inside one `ApplicationRuntime`;
helper functions must not create a fallback graph when that scope is absent.
The daemon server likewise owns its `ApplicationRuntime` and injects the
already-composed `ApplicationGraph` into request/task state. `DaemonState`
borrows that graph only while composing its explicit services and task
capabilities; it must not retain the whole graph as a runtime service locator.
It must not inspect a context variable, construct a fallback runtime, or retain
the lifecycle owner after composition.

The `nuself.application` package root is an import-light namespace. The package
contains only authority lifecycle, the complete graph root, and genuine
cross-domain use cases; concrete domain factories and immutable domain bundles
belong to their domain packages. The root does not grow a second catalog of the
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
evaluation surfaces obtain the concrete graph from `agent.chat.composition`.
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
The CLI root resolves authority once, owns one `ApplicationRuntime`, and binds
it for the complete dispatch lifetime. Initialized CLI and REPL adapters borrow
its graph through parameter-free `cli_application()`; they must not repeatedly
pass or resolve the already-selected authority. No domain-specific composition
aliases mirror individual graph fields. Parameter-free `cli_backend()` remains
the narrow exception for explicit storage infrastructure commands and must not
be used by domain handlers.
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
The service does not retain a model advancer. An explicit advance operation
receives either the narrow advancer protocol for that call or a structured step
already produced by an orchestrator; dependency source must not vary between a
hidden constructor fallback and the operation input. Input resolution must
produce one concrete step or raise before mutation, so persistence and audit
code operate on a non-optional domain value rather than repeat fallback checks.
Pause, resume, resolve, and archive remain explicit Reason use cases, while the
shared transition rule owns their common ID-or-index resolution, validation,
persistence, and audit path. Public semantic names must not require duplicate
adapter logic.
Reason persistence exposes thread-scoped ordered step listing to the service;
it does not expose an otherwise unused raw step lookup. Backend collections
already exist when composed, so the repository has no no-op `ensure()` method.
Modules do not declare unused loggers or storage-version markers. Logging uses
the observed event/audit boundaries actually invoked by the runtime, and
storage versions exist only where a persisted decoder or schema enforces them.
Tool middleware produces the validated `ToolOutcome` value directly. Test-only
success/failure factory spellings are not part of the runtime API; result/error
exclusivity remains enforced by the dataclass invariant.
Domain-local validation types are reused through existing domain dependencies;
modules do not redeclare identical Pydantic constraints or alias a concrete
container used only inside one helper.
Chat tools, model-backed advancement, service operations, and output export
reuse that store instead of constructing equivalent authority-scoped adapters.
`PrivateWorkspaceStore.paths(owner_id)` is its sole workspace resolver and has
no filesystem-creation side effect; resource writers create required
directories at their actual persistence boundary. A no-op `ensure()` alias is
not part of the API. Its returned value exposes only distinct path identities:
the owner's export root and the shared authority database. Writers derive
their own child paths from the export root; the workspace API does not carry
unused or root-aliasing convenience fields.
Reason output exposes the operations used by the current flow: plan, direct
manifest lookup, composition, and job paths. It has no synchronous start/resume
aliases or directory-wide listing API when no process surface consumes them.
Composition is admitted through the daemon scheduler's reason resource lane;
there is no orphaned export `.lock` protocol alongside that scheduler.
Reason output exposes one validated `job_paths(thread_id, job_id)` operation
for its owned artifact layout. Its own methods and daemon execution reuse that
operation instead of adding private pass-throughs or reconstructing manifest
paths. Job submission is a direct sink call with failure isolation at that
boundary; a one-call closure is not an application capability.
Cooldown mutation is a reason
service use case; scheduling must not receive or expose the repository merely
to persist it. Daemon workers may own queues and workspace adapters, but must
not create or infer a second reason persistence graph. Agent reason tools
receive the export workspace capability from chat composition and never resolve
runtime paths to construct it.
`ReasonAdvancer` receives workspace, persona repository, trace recorder, and
resolved paths from application composition. `ReasonScheduler` requires the
selected authority root for correctly scoped observation,
receives the existing single-operation advancer protocol as a required
capability, and never depends on or constructs the concrete model-backed
implementation. Missing advancement capability is an invalid composition, not
a silently disabled scheduler mode.

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
`runtime.cleanup`; related Audit, Event, and Job facilities use owned runtime
subpackages. Files use precise single-word responsibility names; `model.py` is
not mandatory and must not replace a more informative name such as
`definition`, `message`, `publisher`, `payload`, `catalog`, or `policy`. New
catch-all `utils`, `helpers`, or `common` modules are
forbidden. Existing modules with those names must remain narrowly scoped.

Logging infrastructure lives in the top-level `nuself.log` package. Its
`record`, `store`, `reader`, and `warning` modules separately own the immutable
codec, filesystem writes, filesystem reads, and terminal-warning contracts.
The package root is empty: it is not a compatibility or convenience facade.

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
