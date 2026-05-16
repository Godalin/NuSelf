# Trace Spec

Status: TODO. Planned for v0.2.0.

## Purpose

Trace is NuSelf's thought provenance database. It records how important thoughts, answers, memories, reflections, reason steps, and decisions were derived.

Trace must not store hidden raw model chain-of-thought. It stores system-level provenance: inputs, evidence, public summaries, participants, decision points, outputs, and links.

## Storage Contract

TODO: implement file-backed storage under:

```text
private/traces/traces/{trace_id}.json
private/traces/links/{link_id}.json
```

Machine-readable records store timezone-aware ISO timestamps. Human-readable CLI output renders timestamps in the current system timezone per `cli-interaction.md`.

## ThoughtTrace

TODO: define a typed domain model with these fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable trace id |
| `kind` | string | `chat_answer`, `memory_update`, `reflection`, `reason_thread`, `reason_step`, `promotion`, or `decision` |
| `title` | string | Short human-readable title |
| `summary` | string | What this trace explains |
| `inputs` | list[string] | Input artifact refs or short descriptions |
| `evidence_refs` | list[string] | Memory/source/thread/reflection/reason refs used as evidence |
| `derived_from` | list[string] | Prior trace or artifact ids this trace depends on |
| `outputs` | list[string] | Artifacts produced or changed |
| `participants` | list[string] | Agents, selves, or subsystems involved |
| `decision_points` | list[string] | Durable decision summaries, not hidden chain-of-thought |
| `thread_id` | string \| null | Related chat thread when applicable |
| `visibility` | string | `private`, `shareable`, or `internal` |
| `created_at` | string | Creation timestamp |

## TraceLink

TODO: define a typed relation model with these fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable link id |
| `source_id` | string | Source trace or artifact id |
| `target_id` | string | Target trace or artifact id |
| `relation` | string | `supports`, `derived`, `contradicts`, `revises`, `summarizes`, `triggered`, or `cites` |
| `summary` | string | Short relation explanation |
| `created_at` | string | Creation timestamp |

## Recording Requirements

v0.2.0 TODO:

- Reason thread creation creates `kind=reason_thread`.
- Reason advance creates `kind=reason_step`.
- Reflection promotion into reason creates `kind=promotion`.
- Important chat answers create `kind=chat_answer` when the answer uses memory, source, reflection, or reason context.

## CLI Contract

TODO: add commands:

```text
nuself trace list [--kind <kind>] [--visibility private|shareable|internal|all] [--json]
nuself trace show <id_or_index> [--by-index] [--json]
nuself trace search <query> [--kind <kind>] [--json]
```

Human-readable output must use the shared record renderer style from `cli-interaction.md`.

Default list output includes `private` and `shareable` traces, excluding `internal` unless requested.

## REPL Contract

TODO: add interactive commands:

```text
:trace
:trace list
:trace show <id_or_index>
:trace search <query>
```

REPL output must match CLI formatting as closely as possible.

## Search Contract

TODO: first implementation may use deterministic substring search over title, summary, inputs, evidence refs, outputs, and decision points.

Vector or graph search is out of scope for v0.2.0.

## Privacy Contract

- Default visibility is `private`.
- `internal` traces are excluded from default list/search/export.
- `shareable` traces must avoid exposing private raw context beyond intentionally summarized provenance.

## Non-Goals

- No hidden raw model chain-of-thought.
- No full transcript duplication.
- No graph visualization in v0.2.0.
- No requirement that every log event becomes a trace.
