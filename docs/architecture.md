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
session orchestration. The daemon owns long-lived local processes, JSONL
transport, background workers, and live activity subscriptions. Both
boundaries call typed services rather than embedding domain behavior.

Conversation execution lives under `nuself.agent.chat`. LangGraph coordinates
stateful turns and LangChain supplies model and tool abstractions. NuSelf-owned
code adds domain semantics such as personal-memory retrieval, evidence
handling, persona discussion, and response presentation.

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

Major domains are:

- **Memory and ingestion** — authoritative personal records, sources,
  candidates, profile items, relations, and rebuildable search projections.
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
domain records are preserved independently from derived indexes so projections
can be rebuilt without changing identity or evidence.

SQLite and file-backed stores are accessed through explicit storage and
repository boundaries. Runtime paths and configuration precedence are governed
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
