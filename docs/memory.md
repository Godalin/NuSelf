# Memory Guide

NuSelf separates conversation history, durable memory, profile facts, imported
sources, and query views. This keeps raw chat from automatically becoming
long-term memory.

All personal data lives under the selected authority. The default user
authority is `~/.nuself/`; an explicit workspace uses
`<workspace>/.nuself/`. SQLite state lives at
`<authority-root>/nuself.sqlite`.

## Inspect Memory

```bash
uv run nuself memory list
uv run nuself memory preview
uv run nuself memory show <id>
uv run nuself memory search "query"
uv run nuself memory stats
```

Visible list indexes are convenient for interactive use; stable IDs are better
for scripts and cross-references.

## Add And Edit

Create a durable entry:

```bash
uv run nuself memory add \
  --type belief \
  --body "Small, explicit interfaces are easier to maintain."
```

Inspect command-specific fields:

```bash
uv run nuself memory add --help
uv run nuself memory edit --help
uv run nuself memory delete --help
uv run nuself memory types
```

Memory types include beliefs, preferences, experiences, goals, concepts, and
other registered domain categories. Use the CLI registry rather than copying a
stale type list into scripts.

## Curator And Review Queue

Producers such as conversation submit selected evidence through the generic
memory observation API. The curator examines pending observations and produces
typed actions. Depending on configuration and confidence, candidates may be
promoted automatically or remain available for review.

Run one curation cycle:

```bash
uv run nuself memory update
```

Review pending candidates:

```bash
uv run nuself memory review list
uv run nuself memory review show <candidate-id>
uv run nuself memory review accept <candidate-id>
uv run nuself memory review reject <candidate-id>
```

Use `--help` for index selection and batch operations.

## External Source Documents

Place Markdown or plain-text material under the selected authority's
`sources/`, then ingest a
file or directory:

```bash
uv run nuself source ingest .nuself/sources/notes.md --tag notes
uv run nuself source ingest .nuself/sources/archive --tag archive
```

Ingestion is append-only. Unchanged revisions are reused; changed content gets
a new source ID, and the Source API does not replace or delete prior revisions.

Inspect imported sources and chunks:

```bash
uv run nuself source list
uv run nuself source show <source-id>
uv run nuself source chunks <source-id>
uv run nuself source search "citation"
```

Source is an independent external-knowledge library. It does not create
personal memories or profile candidates. Chat searches it only when the Agent
calls a Source tool.

## Relations And Graph

NuSelf derives relation and symbolic graph projections from accepted memory:

```bash
uv run nuself memory relations
uv run nuself memory graph nodes
uv run nuself memory graph edges
uv run nuself memory graph search "retrieval"
```

Graph and relation views are computed directly from authoritative SQLite
records, so they do not require a separate rebuild step.

## Optimize Existing Memory

Run the optimizer manually:

```bash
uv run nuself memory optimize
uv run nuself memory optimize --limit 100
```

Optimizer output passes through the same typed candidate boundary as ordinary
curation. Inspect the review queue after a run.

## Export And Import

JSON memory exchange:

```bash
uv run nuself memory export -o backup/memory.json
uv run nuself memory import backup/memory.json
```

Whole-system thought packs:

```bash
uv run nuself pack export backup
uv run nuself pack inspect .nuself/exports/backup.sqlite
```

Keep independent backups of the selected authority. Export formats are useful portability
tools, not automatic backup scheduling.

## Privacy Boundary

- Default tests and CI never read real user or workspace authorities.
- Opt-in live API tests use fixed synthetic prompts and do not load personal
  memory, threads, sources, personas, or runtime prompts.
- Effective configuration and diagnostics redact credentials.
- NuSelf is local-first, but configured model calls send selected context to
  the endpoint you choose.

The authoritative memory model and curation rules live in
[`spec/memory.md`](spec/memory.md). Storage and migration rules live in
[`spec/storage-v2.md`](spec/storage-v2.md).
