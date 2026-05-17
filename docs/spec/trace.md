# Trace Spec

Status: ready for first v0.2.0 implementation.

## Purpose

Trace is NuSelf's thought provenance database. It records how important thoughts, answers, memories, reflections, reason steps, and decisions were derived after chat history is compressed and memory is curated.

Trace is not hidden raw model chain-of-thought. It stores inspectable system-level provenance:

- user-visible or summarized inputs;
- evidence references;
- retrieved memories, sources, reflections, and reason records;
- participant agents, selves, or subsystems;
- durable decision summaries;
- outputs and changed artifacts;
- links between traces and artifacts.

## Design Principles

- **Provenance, not transcript duplication**: a trace summarizes why an artifact exists; it does not copy a whole chat transcript.
- **Structured enough to query**: records are JSON files with stable typed fields.
- **Human-readable by default**: CLI and REPL output must use the shared record renderer style from `cli-interaction.md`.
- **Privacy first**: default visibility is `private`; `internal` traces are hidden from default list/search/export.
- **Append-friendly**: traces are durable records. Later traces can revise or link to earlier traces instead of mutating history casually.
- **No hidden reasoning capture**: decision points are public summaries of system decisions, not private token-level reasoning.

## Storage Contract

Trace storage lives under:

```text
private/traces/
  traces/{trace_id}.json
  links/{link_id}.json
  index.json
```

Rules:

- `traces/` contains one `ThoughtTrace` JSON object per file.
- `links/` contains one `TraceLink` JSON object per file.
- `index.json` is derived and rebuildable from `traces/` and `links/`.
- Record timestamps are timezone-aware ISO strings.
- Human-readable output renders timestamps in the current system timezone per `cli-interaction.md`.
- Repository writes must be atomic enough for local CLI use: write to a temporary sibling file, then replace the target file.
- Invalid JSON files are skipped by list/search but surfaced by a dev diagnostic later. First implementation may ignore invalid files silently in normal commands.

## IDs

Trace ids should be stable, readable enough for CLI use, and collision-resistant.

Recommended format:

```text
trace-YYYYMMDDTHHMMSSffffffZ-<shorthex>
tracelink-YYYYMMDDTHHMMSSffffffZ-<shorthex>
```

Rules:

- Full ids are stored in JSON.
- CLI list output assigns temporary 1-based display indexes sorted by `created_at`.
- Commands accepting `<id_or_index>` resolve an exact id first, then a visible list index.
- Index resolution must respect the same filters as the command view when filters are supplied.

## ThoughtTrace

Required JSON shape:

```json
{
  "id": "trace-...",
  "kind": "chat_answer",
  "title": "...",
  "summary": "...",
  "inputs": [],
  "evidence_refs": [],
  "derived_from": [],
  "outputs": [],
  "participants": [],
  "decision_points": [],
  "thread_id": "default",
  "visibility": "private",
  "created_at": "2026-05-18T12:34:56.000000+08:00",
  "metadata": {}
}
```

Fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable trace id |
| `kind` | enum | Trace kind |
| `title` | string | Short human-readable title |
| `summary` | string | What this trace explains |
| `inputs` | list[string] | Input artifact refs or short sanitized descriptions |
| `evidence_refs` | list[string] | Memory/source/thread/reflection/reason refs used as evidence |
| `derived_from` | list[string] | Prior trace or artifact ids this trace depends on |
| `outputs` | list[string] | Artifacts produced or changed |
| `participants` | list[string] | Agents, selves, or subsystems involved |
| `decision_points` | list[string] | Durable decision summaries, not hidden chain-of-thought |
| `thread_id` | string \| null | Related chat thread when applicable |
| `visibility` | enum | `private`, `shareable`, or `internal` |
| `created_at` | string | Timezone-aware creation timestamp |
| `metadata` | object | Small extension field for future typed details |

Allowed `kind` values for v0.2.0:

- `chat_answer`
- `memory_update`
- `reflection`
- `reason_thread`
- `reason_step`
- `promotion`
- `decision`

Allowed `visibility` values:

- `private`: default, visible in normal local commands.
- `shareable`: safe to include in future share/export flows.
- `internal`: hidden from default list/search/export unless explicitly requested.

Validation rules:

- `id`, `kind`, `title`, `summary`, `visibility`, and `created_at` are required.
- `title` and `summary` must be non-empty after stripping.
- List fields default to empty lists.
- `metadata` defaults to `{}`.
- Unknown `kind` or `visibility` values are rejected by write APIs.

## TraceLink

Required JSON shape:

```json
{
  "id": "tracelink-...",
  "source_id": "trace-...",
  "target_id": "trace-...",
  "relation": "derived",
  "summary": "...",
  "created_at": "2026-05-18T12:34:56.000000+08:00",
  "metadata": {}
}
```

Fields:

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Stable link id |
| `source_id` | string | Source trace or artifact id |
| `target_id` | string | Target trace or artifact id |
| `relation` | enum | Relationship type |
| `summary` | string | Short relation explanation |
| `created_at` | string | Timezone-aware creation timestamp |
| `metadata` | object | Small extension field for future typed details |

Allowed `relation` values for v0.2.0:

- `supports`
- `derived`
- `contradicts`
- `revises`
- `summarizes`
- `triggered`
- `cites`

Validation rules:

- `id`, `source_id`, `target_id`, `relation`, `summary`, and `created_at` are required.
- `summary` must be non-empty after stripping.
- First implementation does not need to enforce that `source_id` and `target_id` both exist locally because one side may be an external artifact id.

## Repository Contract

`TraceRepository` owns local persistence.

Required operations:

```text
save_trace(trace) -> ThoughtTrace
get_trace(id_or_index, filters) -> ThoughtTrace
list_traces(kind=None, visibility=default) -> list[ThoughtTrace]
search_traces(query, kind=None, visibility=default) -> list[ThoughtTrace]
save_link(link) -> TraceLink
links_for(trace_id) -> list[TraceLink]
reindex() -> Path
```

Default visibility filter:

```text
private, shareable
```

`internal` records appear only when `visibility=internal` or `visibility=all`.

Sorting:

- Lists sort by `created_at` ascending for stable index assignment unless a command explicitly requests another order later.
- Search results sort by deterministic score descending, then `created_at` ascending.

Search:

- First implementation uses deterministic case-insensitive substring search.
- Searchable fields: `title`, `summary`, `inputs`, `evidence_refs`, `derived_from`, `outputs`, `participants`, and `decision_points`.
- Vector search and graph search are out of scope for v0.2.0.

## Service And Tool-Facing Interface

Trace is a subsystem service, not only a repository.

Layers:

- `ThoughtTrace` / `TraceLink`: domain models and validation.
- `TraceRepository`: file-backed persistence and index rebuild.
- `TraceRecorder`: service interface used by other subsystems to create traces and links.
- `TraceQueryService`: service interface for list/show/search.
- Trace renderers: human-readable CLI/REPL output.
- Tool-facing adapter: read-only search/show/list tools for agents in v0.2.0.

Rules:

- Other subsystems must create traces through `TraceRecorder`, not by writing trace files directly.
- Agents should call tool-facing trace interfaces, not `TraceRepository`.
- `TraceRecorder` decides deterministic create/skip policy from structured runtime facts. LLMs may later help polish titles or summaries, but the first implementation should not rely on an LLM to decide whether infrastructure records are written.
- Tool-facing trace results must be concise, privacy-aware, and safe to include in LLM prompts.

Required first service methods:

```text
record_reason_thread_created(...)
record_reason_step(...)
record_reflection_promoted(...)
record_chat_turn(...)
link(source_id, target_id, relation, summary)
```

Required first read/query methods:

```text
list_traces(...)
show_trace(...)
search_traces(...)
links_for(...)
```

## Recording Requirements

v0.2.0 must record traces for:

- reason thread creation: `kind=reason_thread`;
- reason advance: `kind=reason_step`;
- reflection promotion into reason: `kind=promotion`;
- important chat turns when the answer used memory, source, reflection, or reason context: `kind=chat_turn`.

Important chat turn rule:

- Do not trace every chat turn.
- Trace a chat turn when retrieved context materially influenced the reply or when the turn creates/changes a durable artifact.
- The trace must include a user input ref or sanitized user input summary in `inputs`.
- The trace must include an assistant output ref or sanitized answer summary in `outputs`.
- The trace should reference the chat thread and relevant evidence refs, not duplicate the whole turn.

Reason integration:

- Reason owns durable long-run state.
- Trace owns provenance.
- Every non-trivial `ReasoningStep` writes a `ThoughtTrace` with `outputs` containing the step id and updated thread id.

Reflection integration:

- Promoting a reflection into a reason thread writes a `promotion` trace.
- The promotion trace links the reflection candidate/entry to the new reason thread.

## CLI Contract

Required commands:

```text
nuself trace list [--kind <kind>] [--visibility private|shareable|internal|all] [--json]
nuself trace show <id_or_index> [--by-index] [--json]
nuself trace search <query> [--kind <kind>] [--visibility private|shareable|internal|all] [--json]
```

Output rules:

- Human-readable output uses the shared record renderer style from `cli-interaction.md`.
- List rows show index, kind tag, visibility, title, and local display timestamp.
- Show output includes summary, inputs, evidence refs, derived_from, outputs, participants, decision points, and related links.
- JSON output returns stable machine-readable objects using stored field names.
- Empty lists/searches print a concise empty-state line.

## REPL Contract

Required interactive commands:

```text
:trace
:trace list
:trace show <id_or_index>
:trace search <query>
```

Rules:

- `:trace` defaults to `:trace list`.
- REPL output should match CLI formatting as closely as possible.
- REPL commands do not mutate trace records in v0.2.0 except through future reason/reflection flows.

## Privacy Contract

- Default visibility is `private`.
- `internal` traces are excluded from default list/search/export.
- `shareable` traces must avoid raw private context beyond intentionally summarized provenance.
- Trace records may contain sensitive summaries; they stay under `private/` and are not committed.
- Future transcript export may include trace summaries only when explicitly requested.

## Logging Contract

Trace writes should emit structured logs:

- component: `memory` or a future `trace` component only if `logs.py` is expanded;
- event examples: `trace_saved`, `trace_link_saved`, `trace_reindexed`;
- logs must not duplicate large trace summaries or raw inputs.

First implementation may use the existing `memory` log component to avoid widening the log component enum.

## Non-Goals

- No hidden raw model chain-of-thought.
- No full transcript duplication.
- No graph visualization in v0.2.0.
- No requirement that every log event becomes a trace.
- No background trace extraction scheduler.
- No vector or graph search in the first implementation.
