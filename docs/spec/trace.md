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
- **Human-readable by default**: CLI and REPL output must use the shared record renderer style from `cli.md`.
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
- Human-readable output renders timestamps in the current system timezone per `cli.md`.
- Repository writes must be atomic enough for local CLI and concurrent tool use:
  write to a unique temporary sibling file, then replace the target file.
- Writes in the same local process are serialized per trace repository root so
  concurrent trace recording cannot race while rebuilding `index.json`.
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
- CLI list output assigns temporary 0-based display indexes sorted by `created_at`.
- Commands accepting `<id_or_index>` resolve an exact id first, then a visible list index.
- Index resolution must respect the same filters as the command view when filters are supplied.

## ThoughtTrace

Required JSON shape:

```json
{
  "id": "trace-...",
  "kind": "chat_turn",
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

- `chat_turn`
- `memory_update`
- `reflection`
- `reason_thread`
- `reason_step`
- `promotion`
- `decision`
- `persona_prompt_created`
- `persona_disabled`
- `persona_enabled`

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
traces_for_artifact(artifact_ref, visibility=default) -> list[ThoughtTrace]
save_link(link) -> TraceLink
links_for(trace_id) -> list[TraceLink]
links_for_artifact(artifact_ref) -> list[TraceLink]
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

Artifact references:

- `traces_for_artifact(artifact_ref)` returns traces that directly mention the exact artifact reference in `inputs`, `evidence_refs`, `derived_from`, `outputs`, or string metadata values.
- `links_for_artifact(artifact_ref)` returns trace links whose `source_id` or `target_id` exactly equals the artifact reference.
- Artifact references are stable strings such as `memory:<entry_id>`, `reflection:<entry_id>`, `reason:<thread_id>`, `reason_step:<step_id>`, `persona_prompt:<prompt_id>`, and `trace:<trace_id>`.
- Artifact lookup is a read/query feature. It does not imply ownership or deletion authority.

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
traces_for_artifact(...)
links_for(...)
links_for_artifact(...)
```

## Recording Requirements

v0.2.0 must record traces for:

- reason thread creation: `kind=reason_thread`;
- reason advance: `kind=reason_step`;
- reflection creation: `kind=reflection`;
- reflection promotion into reason: `kind=promotion`;
- important chat turns when the answer used memory, source, reflection, or reason context: `kind=chat_turn`;
- memory curator auto-accept: `kind=memory_update`;
- persona prompt creation: `kind=persona_prompt_created`;
- persona disable: `kind=persona_disabled`;
- persona enable: `kind=persona_enabled`.

Important chat turn rule:

- Do not trace every chat turn.
- Trace a chat turn when retrieved context materially influenced the reply or when the turn creates/changes a durable artifact.
- First implementation treats non-empty final `evidence_references` as the deterministic signal that retrieved context materially influenced the reply.
- The trace must include a user input ref or sanitized user input summary in `inputs`.
- The trace must include an assistant output ref or sanitized answer summary in `outputs`.
- The trace should reference the chat thread and relevant evidence refs, not duplicate the whole turn.
- Chat trace creation is best-effort infrastructure work. A trace write failure must emit a concise log and must not fail the chat turn.

Reason integration:

- Reason owns durable long-run state.
- Trace owns provenance.
- Every non-trivial `ReasoningStep` writes a `ThoughtTrace` with `outputs` containing the step id and updated thread id.

Reflection integration:

- Creating a reflection writes a `reflection` trace.
- Promoting a reflection into a reason thread writes a `promotion` trace.
- The promotion trace links the reflection candidate/entry to the new reason thread.

Memory integration:

- Creating a memory entry through the curator's auto-accept writes a `memory_update` trace.
- The trace's `evidence_refs` links to the source `chat_turn` trace when available, enabling provenance from memory entry back to the original conversation.
- The trace is recorded best-effort: failure does not prevent the memory entry from being saved.

## CLI Contract

Required commands:

```text
nuself trace list [--kind <kind>] [--visibility private|shareable|internal|all] [--json]
nuself trace show <id_or_index> [--json]
nuself trace search <query> [--kind <kind>] [--visibility private|shareable|internal|all] [--json]
nuself trace related <artifact_ref> [--visibility private|shareable|internal|all] [--json]
```

Output rules:

- Human-readable output uses the shared record renderer style from `cli.md`.
- List rows show index, kind tag, visibility, title, and local display timestamp.
- Show output includes summary, inputs, evidence refs, derived_from, outputs, participants, decision points, and related links.
- Related output lists traces and direct links that mention the exact artifact reference.
- JSON output returns stable machine-readable objects using stored field names.
- Empty lists/searches print a concise empty-state line.

## Artifact Deletion And Trace Retention

Trace records are provenance, not owned child data of memory, reflection, reason, persona, or chat artifacts.

Rules:

- Deleting or archiving a business artifact must not cascade-delete trace records.
- A trace may continue to reference an artifact that has since been deleted, archived, dismissed, or otherwise made inactive.
- User-facing trace renderers and agent-facing trace tools must tolerate tombstoned or missing artifact references.
- Cleanup tooling, when added, must be explicit and dry-run first. It may hide, tombstone, or mark trace records, but it must not physically delete upstream evidence traces by default.
- Physical trace deletion is a future maintenance operation, not part of normal artifact deletion in v0.2.0.

## REPL Contract

Required interactive commands:

```text
:trace
:trace list
:trace show <id_or_index>
:trace search <query>
:trace related <artifact_ref>
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
