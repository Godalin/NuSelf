# NuSelf Architecture

This document describes current high-level system boundaries and their
rationale. It is an orientation map, not a behavioral contract. Authoritative
behavior lives in [`spec/`](spec/).

## Product Direction

NuSelf is a local-first AI mirror for personal memory, ideas, experience, and
reasoning. Its architecture follows four principles:

- preserve evidence and uncertainty instead of inventing personal claims;
- keep authoritative private records separate from rebuildable projections;
- use deterministic code for infrastructure and policy boundaries, and models
  for bounded interpretive judgment;
- prefer LangChain and LangGraph runtime contracts over parallel agent
  protocols.

## Runtime Shape

```text
CLI / interactive REPL
        |
        v
explicit user/workspace scope resolution
        |
        v
local daemon and direct-mode composition
        |
        +--> conversation graph and agent tools
        +--> memory, persona, reflection, reason, and trace services
        +--> background jobs and notification delivery
        |
        v
repositories, SQLite/file storage, logs, and private artifacts
```

`nuself.cli` owns command parsing, one-shot command adapters, and interactive
session orchestration. One daemon process owns JSONL transport, a unified
bounded task scheduler, and live activity subscriptions. Both
boundaries call typed services rather than embedding domain behavior.

Interactive presentation is replaceable. Backend operations publish typed
runtime events and request confirmation through injected ports. Terminal
rendering, daemon activity transport, tests, and a future web frontend are
adapters over those contracts; backend modules do not import terminal UI code.

Persistent conversation state and its repository live in the isolated
`nuself.conversation` domain and are owned once by `ApplicationGraph`.
Conversation execution lives under `nuself.agent.chat` and borrows that store.
A separate read-only history service returns bounded immutable excerpts to
reflection, reasoning, or future consumers; those domains never receive the
conversation store, state records, locks, or schema. After a completed turn
commits, an application projector may submit selected text through memory's
generic durable observation API. Memory owns that inbox and never scans
conversation persistence.
A persistent conversation is distinct from a transient interactive session
and contains ordered turns, a bounded summary, and branch/archive state. A
direct typed NuSelf pipeline coordinates context, response, and state update;
compression is follow-up work after the reply commits and is presented. A
one-shot turn composes one conversation runtime and reuses it for that delayed
compression; it does not rebuild the model/tool/persona resource graph after
presenting the reply.
LangChain supplies the single framework-native model/tool graph. NuSelf-owned
code adds domain semantics such as personal-memory retrieval, evidence
handling, persona discussion, and response presentation.

Application composition supplies two immutable, ownership-specific resource
snapshots: `ConversationResources` for a turn and its nested `ToolResources`
for tools. They are plain typed data, not managers: neither performs dispatch
or owns lifecycle. This keeps constructors small without hiding dependency
authority.
The graph also owns the validated data-administration surface used by CLI
inspection and repair. Process adapters cannot borrow raw collections. When
an interactive operation crosses into an owned worker thread, the same
application authority is bound into that call and remains owned by the outer
CLI lifecycle.

The application package owns authority lifetime, the complete graph root, and
orchestration that genuinely crosses domain boundaries. It is not a horizontal
catalog of concrete domain factories. Chat, Memory, Persona, Reason,
Reflection, and Trace own concrete composition beside their services and
repositories; the application root invokes those factories while retaining one
resource graph. This ownership rule adds no generic composition framework or
base-class hierarchy.

Concrete execution modules use responsibility names: application lifecycle,
Chat engine, and REPL loop. Reason owns its durable export workflow and
Notification owns its evaluation fixtures; daemon and CLI adapters only invoke
those APIs. The neutral `runtime` package remains the sole home for generic
execution infrastructure. Agent Skill resources and their loader are distinct
paths, avoiding a module/package name collision.

A composition helper exists only when it assembles policy or multiple
dependencies for a real consumer; one-line repository constructors and
pass-through accessors are not service APIs. Domain composition receives
already-resolved paths, storage, config, or graph capabilities and must never
reselect authority resources.

Reflection orchestration receives candidate generation, relevance,
organization, discussion, publication, and trace capabilities from its
domain-owned composition. Persona owns its read-only projection from Memory's
public repository contract; neither domain opens the other's persistence or
selects authority resources.
The daemon keeps one scheduler and one resource-serialization mechanism; a
small closed task catalog prevents producer/handler name drift without adding
per-domain schedulers or locks.

## Shared Infrastructure

Cross-cutting communication is classified by delivery semantics instead of
being forced through one generic message bus:

| Kind | Ownership | Purpose |
| --- | --- | --- |
| Request | one handler, optional reply | CLI and daemon operations |
| Event | zero or more subscribers | live in-process or projected activity |
| Job | one worker with durable state | retryable background work |
| Audit record | read-only consumers | structured diagnostics and history |
| Notification | durable adapter fan-out | user-visible delivery |

The runtime package owns handler registration, message envelopes, correlation
context, event publication, and typed job wake-ups. Logs are append-only audit
records, not a command bus. Notification outbox records are delivery state, not
general events. See
[`spec/runtime-infrastructure.md`](spec/runtime-infrastructure.md) and
[`spec/logs.md`](spec/logs.md).

## Domain Boundaries

Non-trivial domains follow the same dependency direction:

```text
CLI / daemon / agent tool adapter
              |
           service
              |
          repository
              |
       storage boundary
```

Typed models describe domain state. Services own user-intent operations and
policy. Repositories own persistence and indexes. Renderers keep terminal and
transcript output consistent. Agent tools expose narrow service capabilities;
agent skills describe when those capabilities should be used.

Concrete models live with their owning domain (`memory.model`,
`profile.model`, `reflection.model`, and `memory.source_model`). NuSelf has no
horizontal `domain` package that separates a model from the repository and
service that own its semantics.

Feature functions declare cross-cutting behavior through orthogonal decorators
for tool identity, component ownership, effects, confirmation, observation,
and audit. Decorators attach immutable policy only. Shared middleware executes
those policies while domain functions remain directly testable callables.

Major domains are:

- **Memory and ingestion** — producer-neutral durable observations,
  authoritative personal records, sources, candidates, profile items,
  relations, and rebuildable search projections.
  See [`spec/memory.md`](spec/memory.md) and
  [`spec/storage-v2.md`](spec/storage-v2.md).
- **Conversation and persona** — context preparation, tool execution, bounded
  multi-perspective discussion, synthesis, and response presentation. See
  [`spec/agent-tools.md`](spec/agent-tools.md) and
  [`spec/persona/`](spec/persona/).
- **Reflection and notification** — background candidate generation,
  relevance decisions, durable outbox state, and delivery adapters. See
  [`spec/reflection.md`](spec/reflection.md) and
  [`spec/notification.md`](spec/notification.md).
- **Reason, trace, and workspace** — durable long-running reasoning, thought
  provenance, and isolated agent scratch storage. See
  [`spec/reason.md`](spec/reason.md), [`spec/trace.md`](spec/trace.md), and
  [`spec/workspace.md`](spec/workspace.md).

## Persistence And Privacy

Installed NuSelf defaults to a durable user authority under `~/.nuself`.
Explicit workspace scope uses `<workspace>/.nuself`; configuration may inherit
user defaults, but persisted state always belongs to exactly one selected
authority. The source checkout is not an implicit data root. Authoritative
domain records remain directly queryable through typed repositories; NuSelf
does not mirror them into continuously rewritten JSON index files.

SQLite is the only authoritative structured-data store. Typed repositories
isolate domain models from SQL, and the validated `nuself data` service gives
users an inspectable/editable surface without exposing internal tables as a
writable API. Configuration, raw source files, logs, explicit exchange files,
runtime coordination, and rebuildable caches remain filesystem artifacts but
are not parallel authorities. Runtime paths and configuration precedence are governed
by [`spec/config.md`](spec/config.md) and [`spec/scope.md`](spec/scope.md);
migration and storage behavior are governed by
[`spec/storage-v2.md`](spec/storage-v2.md).

## Decision Boundaries

Mechanical operations such as parsing, time arithmetic, validation, caps,
cooldowns, persistence, and retries remain deterministic. Interpretive
decisions such as semantic relevance or persona selection may use model
judgment through typed structured outputs, bounded context, safe fallback, and
observable failures.

Prompts express model-facing policy, but code still enforces schemas, security,
approval, durability, and side-effect boundaries. Model judgment never replaces
explicit user approval for destructive or externally visible actions.

## Documentation Authority

- [`current-goal.md`](current-goal.md) tracks the active objective only.
- [`TODOs.md`](TODOs.md) contains unresolved backlog only.
- [`spec/`](spec/) defines current behavior and development policy.
- [`../CHANGELOG.md`](../CHANGELOG.md) records completed user-visible changes.
- Git history preserves completed internal work and superseded design plans.

If this overview conflicts with a specification, the specification is
authoritative and this document must be corrected.
