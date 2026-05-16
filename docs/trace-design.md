# Trace Design

Status: planned for v0.2.0.

## Purpose

Trace is NuSelf's thought provenance system.

Chats are compressed, memory is merged, reflections are archived, and future reason threads will update their summaries over time. Without provenance, NuSelf can become more useful while becoming less able to explain where important thoughts came from.

Trace records the system-level path by which NuSelf arrived at an important answer, memory, reflection, reason step, or decision.

Trace is not raw model chain-of-thought. It should never attempt to preserve hidden token-level reasoning. Instead, it records durable, inspectable artifacts:

- inputs;
- evidence references;
- retrieved memories and sources;
- persona or reason participants;
- decision points;
- intermediate public summaries;
- outputs;
- links to derived artifacts.

## Naming

User-facing name: `trace`.

Internal objects:

- `ThoughtTrace`
- `TraceLink`
- `TraceRepository`
- `TraceRecorder`

Storage:

```text
private/traces/traces/{trace_id}.json
private/traces/links/{link_id}.json
```

## Conceptual Model

Trace is a cross-system record layer:

```text
chat / memory / reflection / reason / notification
        ↓
ThoughtTrace + TraceLink
        ↓
searchable thought provenance database
```

It should be possible to ask:

- Why does NuSelf believe this?
- Which conversation produced this memory?
- Which reflection became this reason thread?
- Which reason step changed this hypothesis?
- Which memories and sources influenced this answer?

## Domain Model

### ThoughtTrace

Core fields:

- `id`
- `kind`: `chat_answer`, `memory_update`, `reflection`, `reason_thread`, `reason_step`, `promotion`, `decision`
- `title`
- `summary`
- `inputs`
- `evidence_refs`
- `derived_from`
- `outputs`
- `participants`
- `decision_points`
- `thread_id`
- `visibility`: `private`, `shareable`, or `internal`
- `created_at`

### TraceLink

Core fields:

- `id`
- `source_id`
- `target_id`
- `relation`: `supports`, `derived`, `contradicts`, `revises`, `summarizes`, `triggered`, or `cites`
- `summary`
- `created_at`

## Recording Policy

v0.2.0 should record traces for:

- reason thread creation;
- reason advance;
- reflection promotion into reason;
- important chat answers when the answer used memory, source, reflection, or reason context.

Later versions can record:

- memory curator write decisions;
- memory optimizer merges;
- notification decisions;
- full reflection candidate pipelines.

## CLI Shape

```text
nuself trace list [--kind <kind>] [--visibility private|shareable|internal|all] [--json]
nuself trace show <id_or_index> [--by-index] [--json]
nuself trace search <query> [--kind <kind>] [--json]
```

Future:

```text
nuself trace graph <id_or_index>
```

## Relationship To Reason

Reason owns durable long-run question state. Trace owns provenance.

Every non-trivial `ReasoningStep` should create a `ThoughtTrace` with:

- `kind=reason_step`;
- `derived_from` including previous reason step ids and linked evidence refs;
- `outputs` including the new step id and updated thread id.

## Non-Goals

- Do not store hidden raw model chain-of-thought.
- Do not duplicate complete chat transcripts.
- Do not require every minor log event to have a trace.
- Do not build graph visualization in the first implementation.
