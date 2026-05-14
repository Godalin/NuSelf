# NuSelf

[中文版 README](README.zh-CN.md)

NuSelf is a local AI mirror project. It is intended to grow into a personal agent with private memory, resumable conversations, lightweight thought-personas, proactive reflection, and controlled notifications.

The current implementation is an early CLI-first system:

- Local `nuself` command.
- Optional local background daemon over a Unix socket.
- A LangGraph-backed memory-aware chat agent that can run one-shot or through the daemon, with tool use for memory search, reflection inspection, and memory curation.
- File-backed memory entries and profile items that can be listed, viewed, added, edited, deleted, searched, and re-indexed.
- File-backed source ingestion for Markdown and plain text under ignored `private/sources/`, plus reviewable candidates extracted from imported chunks.
- Persisted chat threads with compressed conversation context.

LangGraph now backs the conversation runtime. The chat agent can invoke tools to search memory, list and dismiss pending reflection ideas, archive outdated memories, and adjust importance scores. The internal persona system uses a shared competitive discussion flow for both chat and background reflection, with LLM-backed persona nodes generating distinct voices. Email and macOS notifications are supported when configured.

## Project TODOs

Project progress is tracked in [`docs/TODOs.md`](docs/TODOs.md). Short-term implementation focus lives in [`docs/current-goal.md`](docs/current-goal.md).

## Requirements

- Python 3.12 or newer.
- `uv`.

## Install And Run

From the project root:

```bash
uv run nuself --help
```

Run tests:

```bash
uv run pytest
uvx pyright
```

## Configuration

NuSelf configuration is unified in a single YAML file:

```text
private/config.yaml
```

Configuration priority (highest to lowest):
1. `private/config.yaml`
2. Hardcoded defaults in code

### LLM Configuration

```text
llm:
  openai:
    base_url: https://api.openai.com/v1
    api_key: ""        # Leave empty for local fallback
    model: gpt-4.1-mini
```

### Chat Settings

```text
chat:
  context:
    recent_messages: 12
    summary_trigger_messages: 18
    summary_target_chars: 2400
```

### Daemon Intervals

```text
daemon:
  memory_curator:
    interval_seconds: 300
  reflection_scheduler:
    check_interval_seconds: 60
  notification_delivery:
    interval_seconds: 30
```

### Reflection System

```text
reflection:
  scheduler:
    interval_seconds: 3600
    cooldown_seconds: 300
    quiet_start_hour: 22
    quiet_end_hour: 7
    daily_cap: 5
    jitter_percent: 20
    max_pending_entries: 20
  gate:
    relevance_threshold: 0.5
    persona_discussion_threshold: 0.7
  moderator:
    max_discussion_rounds: 10
    moderator_convergence_patience: 5
```

See `examples/private/config.yaml` for a complete annotated example and additional sections (email, macOS notifications, experimental features).

Inspect effective configuration:

```bash
uv run nuself config
```

## Private Directory

Real personal data lives in the ignored root directory:

```text
private/
```

This directory is not committed to Git. It contains local profile notes, memory entries, chat threads, runtime files, daemon logs, derived indexes, and future private configuration.

The repository includes a safe public sample directory:

```text
examples/private/
```

Use the sample directory for documentation, tests, and demos. Do not put real personal memory there.

## Chat

One-shot chat works without a daemon:

```bash
uv run nuself chat
uv run nuself chat --message "hello"
```

The shortest daemon-backed entrypoint is the root command. It connects to the current daemon, or creates one and then connects:

```bash
uv run nuself
uv run nuself --message "hello"
```

If a daemon is running, `chat` sends the message to the daemon:

```bash
uv run nuself daemon start
uv run nuself chat --message "hello from daemon"
uv run nuself daemon stop
```

Require an existing daemon:

```bash
uv run nuself chat --require-daemon --message "hello"
```

Attach to an existing daemon conversation:

```bash
uv run nuself attach
uv run nuself attach --message "continue"
uv run nuself daemon attach
uv run nuself daemon attach --message "continue"
```

Without `--message`, `chat` and `attach` enter interactive mode. When terminal support is available, line editing and arrow-key history are backed by `private/runtime/interactive_history`. Input starting with `:` is treated as an interactive command. Type `:status` for daemon/thread status, `:logs` for recent activity events, and `:memory` or `:mem` to preview current memory entries. Read-only memory inspection shortcuts include `:mem search <query>`, `:mem show <entry-id>`, `:mem candidates`, `:mem candidate <candidate-id>`, `:mem profile <query>`, `:mem sources`, and `:mem source <source-id>`. Type `:q`, `:quit`, `:exit`, or send EOF to leave; unknown commands print interactive help and keep the session open.

Current chat uses a LangGraph-backed conversation runtime that searches memory entries, derived profile items, and imported source chunks, appends turns to `private/threads/default.json`, and compresses older context into a thread summary once the conversation grows. The agent can also invoke tools during conversation: `search_memory` for targeted retrieval, `list_pending_reflections` / `dismiss_reflection` to inspect and manage proactive ideas, and `archive_memory` / `update_memory_importance` to curate durable memory. The memory search is deterministic lexical retrieval with descriptor-aware type hints, type/tag filters, relation expansion over existing memory links, and ranked match reasons; vector and graph indexes are planned as derived retrieval layers.

`private/threads/default.json` is shared working memory for the current NuSelf mind. Multiple terminal attachments to the same daemon share it. The thread store serializes writes with a lock so concurrent turns do not overwrite each other.

The memory curator runs in the background in the daemon and also runs when interactive chat exits. It uses an agent to decide whether new working-memory turns should create, update, or ignore long-term memory. Trivial chat is ignored, similar existing memories should be updated instead of duplicated, and raw chat transcripts are rejected. By default, accepted candidates are automatically promoted to durable memory entries (`auto_accept=True`); you only need to review candidates when you want to edit or reject something. A separate memory optimizer can be run manually, less frequently, to consolidate messy existing entries. Update events are written to `private/logs/memory.log`, and interactive chat prints compact activity lines for new chat, daemon, and memory events.

The current conversation graph is intentionally small: it preserves the CLI and daemon protocol boundary while keeping room for later persona subgraphs and richer agent routing.

## Daemon

Start, inspect, and stop the local daemon:

```bash
uv run nuself daemon start
uv run nuself daemon status
uv run nuself daemon list
uv run nuself daemon logs
uv run nuself daemon attach --message "continue"
uv run nuself daemon stop
uv run nuself daemon restart
```

Structured local logs can also be inspected with:

```bash
uv run nuself logs
uv run nuself logs --component chat --tail 20
uv run nuself logs --component memory --json
uv run nuself logs --component reflection --tail 10
```

Check system health:

```bash
uv run nuself health
```

Quick status overview:

```bash
uv run nuself status
```

Without a subcommand, `daemon` shows daemon subcommand help.

Daemon runtime files are stored under:

```text
private/runtime/
private/logs/
```

The first protocol is JSON lines over a Unix domain socket at `private/runtime/nuself.sock`.

## Notifications

The notification outbox is a generic event bus for "something happened" alerts. It can be used by any background job (reflection with `auto_notify`, memory curator, etc.).

```bash
uv run nuself notify list
uv run nuself notify show <entry-id>
uv run nuself notify show -i <index>
uv run nuself notify send <entry-id>
uv run nuself notify dismiss <entry-id>
uv run nuself notify dismiss -i <index>
uv run nuself notify clear
uv run nuself notify watch          # poll for new entries
```

Notifications include a deep link. Open one directly:

```bash
uv run nuself open --deep-link "nuself://thread/reflections"
```

The macOS adapter delivers pending entries as system notifications via `osascript`. The email adapter reads SMTP credentials from `private/email.toml` and sends via SMTP. Both support dry-run mode for testing.

## Reflection

The daemon runs a proactive reflection scheduler that generates ideas from recent threads, memory entries, and source documents. Ideas are scored for novelty, confidence, urgency, and interruption cost, then debated by a randomized set of internal personas. Approved ideas are stored in `private/reflections/` as first-class entries with `pending`, `dismissed`, or `archived` status.

Reflection ideas can be inspected and managed with:

```bash
uv run nuself reflection list
uv run nuself reflection list --status pending
uv run nuself reflection list --status dismissed
uv run nuself reflection show <id>
uv run nuself reflection show -i <index>
nuself reflection dismiss <id>
nuself reflection archive <id>
```

When `reflection.auto_notify` is enabled in config, a brief notification is also created in the outbox pointing to the new reflection idea.

## Threads

List, inspect, and manage conversation threads:

```bash
uv run nuself thread list
uv run nuself thread show <thread-id>
uv run nuself thread create <thread-id>
uv run nuself thread rename <old-id> <new-id>
uv run nuself thread branch <source-id> <new-id> [--index <n>]
uv run nuself thread archive <thread-id>
uv run nuself thread unarchive <thread-id>
uv run nuself thread archived
uv run nuself thread delete <thread-id>
```

Open a thread in interactive mode:

```bash
uv run nuself open <thread-id>
uv run nuself open <thread-id> --message "hello"
```

In the REPL, switch threads with `:thread <id>`, view recent messages with `:history`, list imported sources with `:sources`, search memory with `:search <query>`, archive the current thread with `:archive`, restore an archived thread with `:unarchive <id>`, list archived threads with `:archived`, and delete the current thread with `:delete`.

## Memory Entries

Chat is the primary source of new memory. After chat turns, NuSelf runs the Memory Curator Agent and prints a `[memory] ...` summary when durable memory changes are created or updated.
Curator decisions are based on discussion depth, quality, and durable signal rather than a fixed number of chat turns.

Manual memory commands remain available as maintenance tools. Memory is stored as clear entries under:

```text
private/memory/entries/
```

Add an entry:

```bash
uv run nuself memory add \
  --body "Prefer explicit assumptions and source-aware reasoning." \
  --tag style
```

`memory add` infers the memory type and title by default. Use `--type` or `--title` only when you need an explicit maintenance override.

List entries:

```bash
uv run nuself memory list
```

Preview recent memory entries:

```bash
uv run nuself memory preview
uv run nuself memory preview --limit 20
```

Show one entry:

```bash
uv run nuself memory show <entry-id>
```

Edit an entry:

```bash
uv run nuself memory edit <entry-id> \
  --title "Clarity matters most" \
  --body "Prefer explicit assumptions, concrete evidence, and source-aware reasoning."
```

Search entries:

```bash
uv run nuself memory search "clarity"
```

Export all memory entries to JSON:

```bash
uv run nuself memory export -o backup/memory.json
uv run nuself memory import backup/memory.json
```

Run the memory curator immediately:

```bash
uv run nuself memory update
```

Consolidate existing memory entries:

```bash
uv run nuself memory optimize
uv run nuself memory optimize --limit 100
```

Delete an entry:

```bash
uv run nuself memory delete <entry-id>
```

List registered memory types:

```bash
uv run nuself memory types
```

Rebuild the derived memory index:

```bash
uv run nuself memory reindex
```

Inspect derived memory relations:

```bash
uv run nuself memory relations
uv run nuself memory relations --relation supersedes
uv run nuself memory relations --source-id <entry-id>
uv run nuself memory relations --target-id <entry-id>
```

Inspect the derived symbolic graph:

```bash
uv run nuself memory graph nodes
uv run nuself memory graph nodes --type belief
uv run nuself memory graph edges
uv run nuself memory graph edges --relation related_to
uv run nuself memory graph edges --source-id <entry-id>
uv run nuself memory graph edges --target-id <entry-id>
uv run nuself memory graph search "graph retrieval"
uv run nuself memory graph search "graph retrieval" --type concept --limit 5
```

The derived memory, relation, and symbolic graph artifacts are written to:

```text
private/derived/memory_index.json
private/derived/relation_index.json
private/derived/symbolic_graph.json
```

## Source Documents

Import Markdown or plain-text source material into ignored local storage:

```bash
uv run nuself source ingest private/sources/my-note.md --tag notes
uv run nuself source ingest private/sources/ --tag archive
```

Imported document metadata is stored under `private/sources/documents/`, and stable chunks are stored under `private/sources/chunks/`.

Inspect imported sources:

```bash
uv run nuself source list
uv run nuself source show <source-id>
uv run nuself source chunks <source-id>
uv run nuself source search "durable citation"
```

Extract reviewable profile candidates from an imported source:

```bash
uv run nuself source extract <source-id>
```

The extraction step creates `profile_fact` candidates in the review queue with structured source evidence. Accepted profile candidates are stored under `private/profile/items/`, and you can inspect them with:

```bash
uv run nuself memory profile list
uv run nuself memory profile search "concise"
uv run nuself memory profile show <profile-id>
```

Profile search supports deterministic filters for `--type`, `--tag`, `--observed-from`, `--observed-to`, and `--valid-on`.

Supported front matter fields are `title`, `date`, `tags`, `origin`, and `privacy`. Source chunk references use the form `source:<source-id>:<chunk-index>`.

`memory reindex` rebuilds `private/derived/memory_index.json`, `private/derived/relation_index.json`, `private/derived/source_index.json`, and `private/derived/profile_index.json` from authoritative memory, source, and profile records.

Delete an imported source and its derived review artifacts:

```bash
uv run nuself source delete <source-id>
```

Delete a derived profile item directly:

```bash
uv run nuself memory profile delete <profile-id>
```

## Memory Entry Types

Supported entry types:

- `source_note`
- `profile_fact`
- `belief`
- `preference`
- `goal`
- `concept`
- `style_trait`
- `episode`
- `open_question`
- `instruction`

## Project Docs

- [Architecture](docs/architecture.md)
- [Development plan](docs/development-plan.md)
- [Agent framework plan](docs/agent-framework.md)
- [Interaction layer plan](docs/interaction-layer.md)
- [System specifications](docs/spec/) — behavioral contracts for CLI, memory, reflection, notifications, etc.
- [Agent instructions](AGENTS.md)

## Development Policy

NuSelf is in active early development. Interfaces are expected to move quickly. Do not preserve obsolete CLI commands, protocol fields, schemas, or Python APIs unless current docs explicitly require compatibility.

When functionality, commands, configuration, runtime behavior, or other user-visible behavior changes, update both [README.md](README.md) and [README.zh-CN.md](README.zh-CN.md) in the same change.
