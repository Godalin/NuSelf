# Memory Guide

NuSelf separates conversation history, durable memory, profile facts, imported
sources, and derived indexes. This keeps raw chat from automatically becoming
long-term memory.

All personal data lives under the ignored project-local `private/` tree.
Current projects normally use `private/nuself.sqlite` as storage authority.

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

The memory curator examines eligible conversation ranges and produces typed
actions. Depending on configuration and confidence, candidates may be promoted
automatically or remain available for review.

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

## Import Source Documents

Place Markdown or plain-text material under `private/sources/`, then ingest a
file or directory:

```bash
uv run nuself memory source ingest private/sources/notes.md --tag notes
uv run nuself memory source ingest private/sources/archive --tag archive
```

Inspect imported sources and chunks:

```bash
uv run nuself memory source list
uv run nuself memory source show <source-id>
uv run nuself memory source chunks <source-id>
uv run nuself memory source search "citation"
```

Extract reviewable profile candidates:

```bash
uv run nuself memory source extract <source-id>
uv run nuself memory profile list
uv run nuself memory profile search "preference"
```

Source deletion and profile deletion are explicit operations; read the
subcommand help before removing data.

## Relations And Graph

NuSelf derives relation and symbolic graph projections from accepted memory:

```bash
uv run nuself memory relations
uv run nuself memory graph nodes
uv run nuself memory graph edges
uv run nuself memory graph search "retrieval"
```

Rebuild derived indexes when diagnosing projection state:

```bash
uv run nuself memory reindex
```

Derived indexes can be rebuilt; the authoritative records cannot.

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
uv run nuself pack inspect private/exports/backup.sqlite
```

Keep independent backups of `private/`. Export formats are useful portability
tools, not automatic backup scheduling.

## Privacy Boundary

- Default tests and CI never read `private/`.
- Opt-in live API tests use fixed synthetic prompts and do not load personal
  memory, threads, sources, personas, or runtime prompts.
- Effective configuration and diagnostics redact credentials.
- NuSelf is local-first, but configured model calls send selected context to
  the endpoint you choose.

The authoritative memory model and curation rules live in
[`spec/memory.md`](spec/memory.md). Storage and migration rules live in
[`spec/storage-v2.md`](spec/storage-v2.md).
