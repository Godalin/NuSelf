# Subsystem Composition Audit

## Scope

This audit reviews authority-scoped composition and production consumers of
`ApplicationGraph`. It asks which capabilities may cross a domain boundary,
which persistence objects are legitimate inputs to owner-controlled workflows,
and which fields let adapters bypass domain policy.

The audit does not propose a universal facade. A repository remains valid
inside its owning domain composition and in explicit projection, recovery,
migration, repair, or data-administration workflows. It is a leak when a
general process adapter receives it merely because the application graph is a
convenient service locator.

## Audit Rules

1. CLI, REPL, agent tools, and request handlers consume user-intent services.
2. Domain-owned workflow composition may consume the narrow repositories it
   coordinates, but the completed workflow should cross the process boundary
   instead of its raw construction ingredients.
3. Chat execution may consume `ConversationStore` because serialized turn
   mutation is its persistence contract. Conversation-management commands
   should consume a separate management service.
4. Projection, recovery, migration, repair, and validated data administration
   may consume narrow persistence ports explicitly. These are not ordinary
   user-intent APIs and must not be folded into a universal domain service.
5. A resource snapshot is a typed capability grant for one consumer. It is not
   a copy of every object constructed for an authority.
6. Application composition owns repository identity and lifecycle, but
   ownership does not imply exposing repositories as `ApplicationGraph`
   fields.

## Current Shape

`ApplicationGraph` currently exposes a mixture of four different layers:

| Layer | Current examples |
| --- | --- |
| Runtime metadata | `paths`, `config` |
| User-intent services | `memory_service`, `sources`, `inbox`, `reason.service`, `reflection.service`, `trace.query`, `data` |
| Persistence and stores | `memory`, `conversations`, `deliveries`, `persona_prompts`, `reflection.repository`, `reason.workspace` |
| Internal workflow inputs | `trace.recorder`, `conversation_history`, memory observation and curator-plan stores |

Because CLI and daemon code both receive this aggregate, its repository fields
act as public capabilities even when a narrower service already exists.
`ToolResources` correctly gives tools `MemoryService`; that protection ends at
the tool boundary and does not protect other adapters.

## Findings

### Memory

**Boundary leak.** `ApplicationGraph` exposes both `memory: MemoryRepositories`
and `memory_service: MemoryService`. Ordinary CLI and REPL operations use
`memory.entries`, `memory.profile`, and `memory.candidates` directly for list,
get, save, delete, review, graph, quarantine, and profile operations. This
makes repository APIs the effective application API and leaves
`MemoryService` as a partial query facade.

**Legitimate internal access.** Curator and optimizer composition coordinate
entries, candidates, profile, observations, and recovery plans. Reflection
candidate generation reads entries and profile. Chat-to-memory projection and
daemon recovery use the observation repository. These consumers need narrow
ports or already-composed workflows; they do not justify granting the complete
repository bundle to CLI, Chat, or the daemon state object.

**Target.** Memory composition should return public services for entry/query
operations, candidate review, profile operations, and maintenance where those
are stable business use cases. It should also compose curator, optimizer,
observation intake/recovery, reflection context, and persona-definition
projection capabilities for their exact consumers. `MemoryRepositories`
should become an internal composition detail and must not be an
`ApplicationGraph` field.

### Conversation

**Mixed responsibility.** `ConversationStore` is correctly required by Chat's
serialized turn execution, but CLI/REPL management also receives the raw store
for list, load, rename, branch, archive, unarchive, and delete.

**Target.** Keep the store in the Chat execution snapshot and behind the
read-only history service. Add a conversation-management service for stable
user-intent lifecycle operations and transcript inspection. Process adapters
receive that service; only Chat composition and explicit administration retain
the store.

### Persona

**Boundary leak.** Persona CLI/REPL management, Chat persona-tool composition,
Reason advancement, and application projection all receive
`PersonaPromptRepository`. This exposes persistence because Persona has no
complete authority-scoped capability composition.

**Target.** Persona should compose a management service, definition provider,
tool provider, and Reason-scoped persona capability around its private prompt
repository and trace dependency. The repository should not appear on
`ApplicationGraph` or in CLI/Reason/Chat signatures.

### Reflection

**Partially correct.** User commands consistently use `ReflectionService`, but
`ReflectionResources` publicly pairs it with `ReflectionRepository` so outer
CLI and daemon composition can build a scheduler.

**Target.** Reflection-owned composition should consume the repository and
return its public service plus a completed scheduler/workflow capability. The
outer process may supply Memory context, Source, Inbox, Delivery, history,
models, and config, but should not receive Reflection persistence merely to
pass it back into Reflection constructors.

### Reason

**Partially correct.** User operations use `ReasonService`; the raw repository
is already private. `ReasonResources.workspace`, however, is exposed broadly
so Chat tools, exports, daemon scheduling, CLI, and REPL can assemble Reason
workflows outside the domain.

**Target.** Keep `ReasonService` public. Move tool/export/advancer composition
behind Reason-owned capability builders or precomposed resource snapshots so
ordinary adapters do not receive `PrivateWorkspaceStore`. Explicit workspace
administration remains a separate infrastructure capability.

### Source, Inbox, Trace, and Data Administration

**Generally correct.** Source exposes `SourceService`; Inbox exposes
`InboxService`; Trace exposes recorder/query services without its repository;
validated storage access is isolated behind `DataAdminService`.

**Follow-up checks.** `InboxService` currently owns persistence construction,
so its internal repository/service layering should be reviewed separately.
That does not justify replacing the service with raw storage. Trace recorder
and query should continue to be granted independently by consumer.

### Delivery

**Boundary leak.** `DeliveryStore` is handed directly to CLI, REPL, daemon, and
Reflection scheduling. User delivery requests and status transitions therefore
use persistence as their application API.

**Target.** Add a Delivery service for request/query/retry user intent and a
separate completed delivery-loop capability for background execution. Keep the
store private to Delivery composition.

### Runtime Metadata

`paths` and immutable `config` are valid process-composition inputs, but their
presence on the same aggregate encourages late composition throughout CLI and
daemon modules. They should live in an authority/runtime snapshot distinct
from domain capability snapshots. This is a clarity issue, not a requirement
to add forwarding accessors.

## Target Composition

The target is a composition tree, not one flat public graph:

```text
ApplicationRuntime
  owns paths, config, backend, and repository identity
  |
  +-- ApplicationServices
  |     conversation management
  |     memory / candidate review / profile
  |     source / persona management
  |     reflection / reason / inbox / delivery / trace query
  |     data administration
  |
  +-- ChatResources
  |     conversation execution store
  |     ToolResources (services only)
  |     trace recorder / persona definitions
  |
  +-- DaemonWorkflows
        memory observation recovery and curator
        reflection scheduler
        reason scheduler/export
        delivery loop
```

These snapshots are constructed once from the same authority graph. They own
no lifecycle and perform no lookup or forwarding. Repository objects remain
lexically inside domain/application composition until injected into a completed
owner-controlled service or workflow.

`ApplicationGraph` may remain as a private composition result owned by
`ApplicationRuntime`, but general adapters should no longer receive it. Outer
adapters borrow the exact service or workflow snapshot required by their role.

## Recommended Migration Order

1. Specify the service and snapshot contracts in `module-boundaries.md`,
   including the distinction between public services and completed workflows.
2. Complete Memory's public services and replace ordinary CLI/REPL repository
   access. Keep curator, reflection context, projection, and maintenance on
   explicit narrow internal ports.
3. Add Persona management/providers and Conversation management services;
   remove their repositories/stores from ordinary adapters.
4. Add Delivery service/workflow composition and internalize
   `DeliveryStore`.
5. Make Reflection and Reason return completed workflow capabilities so outer
   composition no longer borrows their repository/workspace internals.
6. Replace general `cli_application() -> ApplicationGraph` access with narrow
   service snapshots and give daemon construction one completed workflow
   snapshot.
7. Remove repository bundles and internal stores from the public graph shape,
   then add architecture tests that reject those field types and imports in
   CLI, REPL, daemon request handlers, Chat tools, and evaluation adapters.

## Exclusions

- Do not add pass-through service methods solely to mirror every repository
  method. Each public method must represent a stable use case.
- Do not hide migration, repair, projection, recovery, or data-administration
  persistence needs behind the public Memory service.
- Do not add a service locator, dynamic registry, common base service, or
  manager object that performs dispatch.
- Do not reconstruct repositories per snapshot. Every snapshot must reuse the
  one authority-owned object graph.
- Do not combine this boundary migration with retrieval-index, configuration,
  or conversation-durability backlog work.

## Completion Evidence For Implementation

- No production CLI, REPL, daemon request handler, Chat tool, or evaluation
  adapter imports or receives a domain repository or storage class unless it
  is an explicitly documented administration/projection boundary.
- `ApplicationGraph` has no `MemoryRepositories`, `DeliveryStore`,
  `PersonaPromptRepository`, `ReflectionRepository`, or
  `PrivateWorkspaceStore` field exposed to general adapters.
- Chat tools receive `MemoryService` and other domain services only.
- Memory curator, Reflection scheduler, Reason workflows, observation
  projection/recovery, and data administration reuse the original repository
  identity without reopening storage.
- Declarative architecture tests enforce allowed layer imports and graph field
  types.
- `uv run --locked pytest`, `uv run --locked pyright`, and `git diff --check`
  pass.
