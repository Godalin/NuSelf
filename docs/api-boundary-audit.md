# Module API Boundary Audit

Date: 2026-08-01
Scope: `src/nuself/**/*.py` on `dev/v0.3.x` after `f1e194a`

## Standard

An interaction is API-based when the caller receives a typed capability with
only the operations it needs. A repository is an implementation API within its
own domain, but is not automatically a suitable cross-domain API. Composition
code may register explicit names and concrete implementations; runtime and
domain code must not discover authority, mutate another object's private
state, decode another domain's records, or instantiate another domain's
workflow as a fallback.

## Summary

The shared runtime foundation is sound: CLI and daemon requests use sealed
handler registries, feature decorators attach orthogonal policy, runtime events
use typed envelopes, logging uses a shared contract, and the daemon scheduler
dispatches registered handlers without importing domain implementations.

The repository is not yet API-only end to end. The principal structural issue
is that `ApplicationGraph` exposes a backend and concrete repositories as a
public resource bag. This makes correct composition possible but does not make
incorrect cross-domain access impossible. Nine confirmed boundary problems
remain; none is a new data-corruption or release blocker, but the first four
should be addressed before adding more domains.

## Confirmed Findings

### A1 — ApplicationGraph is a concrete service locator (high)

`ApplicationGraph` publicly exposes `StorageBackend`, `ConversationStore`, and
the concrete repositories for memory, notification, persona, reason,
reflection, and trace. CLI, daemon, and application helpers then select and
recompose subsets ad hoc.

Risk: any new module can bypass a domain service, collection policy, audit,
transaction, or lifecycle merely by borrowing `application.backend` or a
repository. Architecture tests currently reject some known imports rather
than enforcing one capability surface.

Minimal correction: keep a private authority resource graph inside
`application`, and expose domain facades (`conversations`, `memory`,
`notifications`, `personas`, `reasons`, `reflections`, `traces`) containing
typed use-case APIs. Only repository factories and migration/admin
infrastructure receive `StorageBackend`.

### A2 — The generic data CLI bypasses every domain API (high)

`cli.commands.data` owns a hard-coded alias table, a partial validator table,
and raw `backend.collection(name)` read/write/delete transactions. It therefore
knows storage collection names and can mutate conversation or memory records
without domain-level cleanup, projections, or audit semantics.

Risk: a wire-valid edit can still violate cross-record invariants; a delete can
leave indexes, relations, traces, or other domain-owned state inconsistent.

Minimal correction: introduce an application-owned `DataAdminService` whose
registry is populated by each domain with inspect/export and optional
validate/edit/delete capabilities. The CLI should know public resource names,
not collection names or wire codecs. Keep an explicitly unsafe raw-storage
inspection command under `dev`, read-only by default.

### A3 — Reflection orchestrates concrete foreign domains (high)

`ReflectionScheduler` accepts concrete `NotificationOutbox` and
`TraceRecorder` implementations, imports persona implementation types, and
constructs `SharedPersonaDiscussionService` inside `reflect()`. Candidate
generation likewise accepts concrete memory/source/profile repositories and
loads global configuration internally.

Risk: reflection silently owns persona/model/config composition, cannot be
extended independently, and can bypass notification or trace policy. Tests
must replace implementations instead of stable capabilities.

Minimal correction: define consumer-owned ports for candidate context,
discussion, publication, provenance, and schedule state. Compose all concrete
implementations once in `application.reflection`; inject language/config as
values.

### A4 — Conversation-to-memory projection still receives the entire graph (high)

`publish_chat_observation()` receives `ApplicationGraph`, reloads the concrete
conversation store, extracts the last two records by positional convention,
and calls a concrete observation repository. Its fallback constructs identity
from message text when persisted state is absent.

Risk: the projector is coupled to both domains' internals and can associate the
wrong pair when a result and latest store state diverge. The fallback is a
test-shaped second behavior with different identity semantics.

Minimal correction: have the conversation commit API return an immutable
`CompletedTurn` DTO. A projector accepting `CompletedTurn` and a narrow
`MemoryObserver` port performs the only conversion; remove the reload and
fallback.

### A5 — Memory candidate persistence hard-codes profile routing (medium)

`MemoryCandidateRepository` both persists candidates and applies them. It
branches repeatedly on the string `profile_fact`, constructs `ProfileItem`,
and invokes the profile repository for create/merge/delete.

Risk: adding a new candidate target requires editing the repository workflow,
and repository persistence is inseparable from cross-domain policy.

Minimal correction: leave candidate CRUD in the repository and move
accept/reject/merge into `MemoryCandidateService`. Supply a sealed target
handler registry or one explicit profile-target port from application
composition.

### A6 — Persona reads memory's concrete model and repository (medium)

`persona.definition.load_persona_definitions()` imports memory search filters,
queries the concrete memory repository, and understands the
`persona_instruction` memory type and payload schema. Persona discussion and
chat persona orchestration also create model-backed services internally and
load configuration when collaborators are omitted.

Risk: memory schema and persona schema evolve together, while default fallback
construction hides model/config dependencies.

Minimal correction: define a `PersonaDefinitionSource` API returning persona
DTOs. Put the memory-to-persona projection in `application.persona`; inject
discussion/activation/synthesis capabilities and resolved settings.

### A7 — Process adapters still recompose repositories and traces (medium)

Several CLI and REPL handlers call `runtime_paths()`, `get_default_backend()`,
and repository factories directly for profile, reflection, trace, reason, and
persona operations. `compose_cli_application()` also retains a fallback that
creates a graph outside the invocation-owned `ApplicationRuntime`.

Risk: one command can create parallel object graphs and bypass teardown or
application-level policy. The default backend cache currently masks much of
the duplication but is not an API guarantee.

Minimal correction: require an invocation-scoped application runtime for every
initialized command and remove the fallback composition path. Handlers call
domain facades only; `scope`, migration, pack, and developer diagnostics remain
explicit infrastructure exceptions.

### A8 — Daemon task routing is registered but weakly typed (medium)

The scheduler itself correctly uses a handler map, but `DaemonTask.kind`,
identity, resource, and payload are free-form strings/objects. `DaemonState`
repeats task-name and resource-name conventions at each producer and validates
payload types only inside handlers.

Risk: new tasks can drift between producer and handler, and resource conflicts
depend on matching string prefixes by convention.

Minimal correction: keep the single scheduler but add a sealed task-definition
catalog whose definitions encode key, payload codec/type, identity builder,
resource builder, priority, and handler. Do not introduce per-domain schedulers
or locks.

### A9 — Evaluation code mutates private implementation state (low)

`notification_eval` constructs `ReflectionScheduler` via `__new__`, assigns
private fields, calls private methods, and selects storage independently.

Risk: evaluation can pass against an impossible runtime object and breaks on
internal refactors instead of API changes.

Minimal correction: construct the real scheduler through an evaluation
composition fixture with fake ports and an in-memory/test backend.

## Package Coverage

| Area | Result | Notes |
| --- | --- | --- |
| `runtime`, `decorators` | clean | Typed handlers, definitions, events, jobs, feature policy, and cleanup are appropriate shared APIs. |
| `logs`, `config`, `llm`, `scope`, `authority` | mostly clean | Correct shared ownership; callers should receive resolved config/model capabilities instead of invoking defaults inside domains. |
| `storage`, `storage_sqlite`, migrations | clean infrastructure | Direct collection/schema access is expected here, not in feature adapters. |
| `conversation` | clean domain API | Store and bounded history service are separated; the application projector remains finding A4. |
| `memory`, `profile` | partial | Profile port is a good pattern; candidate application still hard-codes profile routing (A5). |
| `persona` | partial | Typed domain models exist, but definition loading and default model composition cross boundaries (A6). |
| `reason` | mostly API-based | Service/repository separation is sound; trace/persona collaborators are still concrete and default prompt-agent construction hides a dependency. Address with the same ports/config pass, not a separate framework. |
| `reflection` | needs work | Most concentrated cross-domain orchestration problem (A3). |
| `notification` | mostly API-based | Outbox/delivery adapter split is sound; adapter constructors should receive resolved paths/config rather than rediscover them. |
| `trace` | clean | Recorder/query services provide a stable API; consumers should type against narrow recorder/query ports. |
| `agent`, `agent.chat`, `agent.tools` | partial | Decorated tools are good; `ToolResources` exposes concrete repositories/services and chat still resolves config/default model collaborators. |
| `daemon` | structurally sound | One process and one scheduler are correct; task contracts need typing (A8), while `DaemonState` remains an oversized composition root. |
| `cli`, `cli.repl` | needs work | Handler registry is good; data access and repeated composition bypass the application API (A2, A7). |
| `tui`, `repl` | clean adapters | Presentation dependencies point outward and do not own persistence. |
| evaluation modules | needs work | `notification_eval` violates public construction (A9); migration/evaluation-only direct storage should be explicit and isolated. |

## Recommended Order

1. Make the application graph private-by-default and define domain facade
   capabilities. This prevents new bypasses before individual cleanup.
2. Replace raw `data` mutation with a domain-contributed admin API.
3. Fix reflection and the completed-turn projection using narrow ports/DTOs.
4. Separate candidate persistence from candidate application; isolate the
   memory-to-persona projection.
5. Remove CLI/REPL fallback composition and hidden domain config/model lookup.
6. Type the existing daemon task catalog and repair evaluation construction.

These changes should replace existing paths rather than coexist with legacy
forwarders. The target is fewer construction paths and narrower call graphs,
not a general-purpose bus or one interface per method.
