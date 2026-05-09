# NuSelf

[中文版 README](README.zh-CN.md)

NuSelf is a local AI mirror project. It is intended to grow into a personal agent with private memory, resumable conversations, lightweight thought-personas, proactive reflection, and controlled notifications.

The current implementation is an early CLI-first system:

- Local `nuself` command.
- Optional local background daemon over a Unix socket.
- A LangGraph-backed memory-aware chat agent that can run one-shot or through the daemon.
- File-backed memory entries and profile items that can be listed, viewed, added, edited, deleted, searched, and re-indexed.
- File-backed source ingestion for Markdown and plain text under ignored `private/sources/`, plus reviewable candidates extracted from imported chunks.
- Persisted chat threads with compressed conversation context.

LangGraph now backs the conversation runtime, and a gated internal persona skeleton can run on explicit or deep turns. Full persona subgraphs, proactive reflection, email, and macOS notifications are still planned.

## Project TODOs

This checklist is the user-facing progress board for the project. It summarizes the detailed plans in [docs/development-plan.md](docs/development-plan.md), [docs/architecture.md](docs/architecture.md), [docs/agent-framework.md](docs/agent-framework.md), [docs/interaction-layer.md](docs/interaction-layer.md), and [docs/memory-management.md](docs/memory-management.md). When features are completed or the plan changes, update this section together with the implementation and planning docs.

Short-term implementation focus lives in [docs/current-goal.md](docs/current-goal.md). Use it as the active development target before pulling work from the broader backlog below.

### Current Goal

- [x] Complete REPL-shaped TUI, structured logging, and memory inspect polish.
- [x] Add a persona activation gate for explicit requests and high-depth discussion cues.
- [x] Wire the minimal persona skeleton into the conversation runtime internally.
- [x] Keep persona contributions internal while preserving chat, CLI, and daemon payloads.
- [x] Surface compact persona activity summaries in the REPL for activated turns.
- [x] Add deterministic routing for `analyst_self`, `skeptic_self`, and `builder_self`.
- [x] Add one more bounded persona (`historian_self`) and mixed-intent precedence rules.
- [x] Add `care_self` and tune explicit multi-perspective routing.
- [x] Add internal `synthesizer_self` for persona contribution fusion.
- [x] Use synthesized persona insight in internal response planning.

### Project Foundation

- [x] Create a standard `uv` Python project with typed package layout.
- [x] Add `uv run pytest` and `uvx pyright` as baseline validation.
- [x] Keep real personal data under ignored root `private/`.
- [x] Commit safe sample private memory under `examples/private/`.
- [x] Keep English and Chinese README files synchronized for user-visible changes.

### CLI And Daemon

- [x] Add `nuself` CLI entrypoint.
- [x] Add daemon lifecycle commands: `start`, `stop`, `status`, `list`, and `logs`.
- [x] Add Unix socket JSONL daemon protocol.
- [x] Add `chat`, `attach`, and daemon-backed attach flows.
- [x] Make root `nuself` a convenient daemon-backed chat entrypoint.
- [x] Add interactive mode with `:q`, `:memory`, command help, and readline history.
- [x] Add a REPL-shaped terminal interaction layer for status, compact activity events, logs, and clearer chat sessions.
- [x] Add read-only REPL memory inspection commands for entries, candidates, profile items, and sources.
- [x] Add readable terminal renderers for memory list and detail views.
- [x] Add structured local log files and a general `nuself logs` viewer.
- [x] Add named thread creation, branching, renaming, and archival.
- [x] Add deep links that open an existing thread or create a new one.

### Memory System

- [x] Add file-backed memory entries under `private/memory/entries/`.
- [x] Add `memory list`, `show`, `add`, `edit`, `delete`, `search`, `preview`, and `reindex`.
- [x] Add shared default working memory under `private/threads/default.json`.
- [x] Serialize shared working-memory writes with a lock.
- [x] Add context compression for long conversations.
- [x] Add deterministic `MemoryQueryService` for relevant memory retrieval.
- [x] Add background Memory Curator Agent for conversation-derived memory updates.
- [x] Run memory curation after chat turns so conversation is the primary memory source.
- [x] Gate memory curation by discussion depth and durable signal instead of fixed turn count.
- [x] Make curator writes conservative: ignore trivial chat, update duplicates before creating, reject raw transcripts.
- [x] Add manual `memory update`.
- [x] Add low-frequency Memory Optimizer Agent for batch cleanup, merging, and deletion of duplicate long-term memories.
- [x] Add manual `memory optimize`.
- [x] Make manual `memory add` infer type and title through a memory intake agent.
- [x] Add memory candidate review queue: list, show, accept, edit, merge, reject.
- [x] Add real-world temporal fields to entries and candidates.
- [x] Route curator and optimizer proposals through the memory candidate review queue.
- [x] Add source-linked evidence records for memory entries.
- [x] Add open `MemoryObject + MemoryTypeDescriptor` registry for typed memory behavior.
- [x] Add built-in descriptors for preference, belief, episode, and instruction memory.
- [x] Add built-in descriptors for goal and concept memory.
- [x] Add descriptor-aware retrieval heuristics and type/tag filters to memory query tools.
- [x] Add first-pass relation-aware retrieval expansion from existing memory links.
- [x] Add rebuildable relation index derived from existing memory links.
- [x] Add `RelationDescriptor` registry for built-in relation behavior.
- [x] Add rebuildable symbolic graph projection over memory entries and relation edges.
- [x] Add transitive-closure retrieval expansion for transitive symbolic relations.
- [ ] Add derived vector, hybrid, and graph indexes.
- [x] Add open symbolic graph with `RelationDescriptor` rules for support, contradiction, refinement, and dependency.
- [x] Make retrieval expansion respect per-relation `retrieval_rule` (e.g. include both current and superseded vs. direct neighbors only).
- [x] Add graph traversal commands (multi-hop search) using descriptor metadata.
- [x] Add transitive-closure traversal for `transitive=True` relation descriptors.
- [x] Add path-finding commands between specific memory nodes.
- [x] Wire transitive-closure into `MemoryQueryService` automatic context expansion.
- [x] Replace the temporary runtime with a LangGraph conversation graph.
- [x] Add memory stats and richer query commands.

### Ingestion And Knowledge Store

- [x] Add local source ingestion for Markdown and plain text.
- [x] Add source metadata parsing for title, path, date, tags, origin, and privacy.
- [x] Add chunking that preserves source references.
- [x] Add repositories for source documents and chunks.
- [x] Add deterministic source search over imported document chunks.
- [x] Make `memory reindex` rebuild source-derived chunk artifacts.
- [x] Add repositories for profile items.
- [x] Make `memory reindex` rebuild all derived artifacts from authoritative sources.

### Agent Runtime

- [x] Add temporary memory-aware chat agent with OpenAI-compatible `/chat/completions`.
- [x] Add ignored `.env` configuration and committed `examples/.env`.
- [x] Keep deterministic fallback behavior when no API key is configured.
- [x] Add minimal conversation runtime boundary for the LangGraph migration.
- [x] Add typed conversation runtime state and node contracts.
- [x] Replace the temporary runtime with a LangGraph conversation graph.
- [x] Isolate the LangGraph driver boundary and preserve thread state on graph failures.
- [x] Add graph runtime diagnostics for node execution and failures.
- [x] Split conversation tool handling into graph-native routes.
- [x] Harden the graph-native tool extension boundary.
- [x] Close the LangGraph runtime migration slice.
- [x] Add structured response schema with answer text, evidence references, confidence, and epistemic status.
- [x] Add unsupported-claim guard for personal claims without evidence.
- [x] Add tool-based memory search for the conversation agent.
- [x] Make conversation retrieval relation-aware for existing memory links.

### Lightweight Multi-Agent Selves

- [x] Add LangGraph persona subgraph.
- [x] Add minimal internal persona skeleton without changing chat payloads.
- [x] Wire the minimal persona skeleton into the conversation runtime internally.
- [x] Add persona activation gate for explicit requests and high-depth discussion cues.
- [x] Add bounded personas: analyst, skeptic, builder, historian, care, and synthesizer.
- [x] Route only relevant personas per request.
- [x] Make synthesizer the only user-facing voice.
- [x] Store persona instructions and corrections as procedural memory.

### Proactive Reflection And Notifications

- [x] Add low-frequency daemon reflection scheduler with cooldowns and quiet hours.
- [ ] Generate idea candidates from recent threads, memory, and sources.
- [ ] Add relevance gate with novelty, confidence, urgency, cooldown, and interruption cost.
- [x] Add notification outbox with idempotency keys and delivery state.
- [x] Add log-only notification adapter.
- [x] Add macOS notification adapter.
- [x] Add email adapter using ignored private configuration.
- [x] Link notifications to a new or existing conversation.

### Evaluation And Quality

- [x] Add golden conversation fixtures.
- [x] Add local evaluation command.
- [x] Score citation coverage, unsupported personal claims, uncertainty behavior, and style fidelity.
- [ ] Add proactive-notification evaluation cases.

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

## LLM Configuration

NuSelf reads private model settings from the ignored root file:

```text
.env
```

Start from the committed example:

```bash
cp examples/.env .env
```

Then fill in:

```text
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4.1-mini
```

The current client uses an OpenAI-compatible `/chat/completions` API. If `OPENAI_API_KEY` is empty, chat uses a deterministic local fallback that still persists the thread but does not perform real model reasoning.

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

Current chat uses a LangGraph-backed conversation runtime that searches memory entries, derived profile items, and imported source chunks, appends turns to `private/threads/default.json`, and compresses older context into a thread summary once the conversation grows. The memory search is deterministic lexical retrieval with descriptor-aware type hints, type/tag filters, relation expansion over existing memory links, and ranked match reasons; vector and graph indexes are planned as derived retrieval layers.

`private/threads/default.json` is shared working memory for the current NuSelf mind. Multiple terminal attachments to the same daemon share it. The thread store serializes writes with a lock so concurrent turns do not overwrite each other.

Context compression can be tuned in `.env`:

```text
NUSELF_CONTEXT_RECENT_MESSAGES=12
NUSELF_CONTEXT_SUMMARY_TRIGGER_MESSAGES=18
NUSELF_CONTEXT_SUMMARY_TARGET_CHARS=2400
NUSELF_MEMORY_CURATOR_INTERVAL_SECONDS=300
```

The memory curator runs in the background in the daemon and also runs when interactive chat exits. It uses an agent to decide whether new working-memory turns should create, update, or ignore long-term memory. Trivial chat is ignored, similar existing memories should be updated instead of duplicated, and raw chat transcripts are rejected. A separate memory optimizer can be run manually, less frequently, to consolidate messy existing entries. Update events are written to `private/logs/memory.log`, and interactive chat prints compact activity lines for new chat, daemon, and memory events.

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
```

Structured local logs can also be inspected with:

```bash
uv run nuself logs
uv run nuself logs --component chat --tail 20
uv run nuself logs --component memory --json
```

Without a subcommand, `daemon` shows daemon subcommand help.

Daemon runtime files are stored under:

```text
private/runtime/
private/logs/
```

The first protocol is JSON lines over a Unix domain socket at `private/runtime/nuself.sock`.

## Notifications

The daemon runs a reflection scheduler in the background. When conditions pass (interval, cooldown, quiet hours), it writes a reflection intent to the notification outbox:

```bash
uv run nuself notify list
uv run nuself notify show <entry-id>
uv run nuself notify send <entry-id>
uv run nuself notify dismiss <entry-id>
```

Reflection intents include a deep link to the `reflections` thread. Open a notification directly:

```bash
uv run nuself open --deep-link "nuself://thread/reflections"
```

The macOS adapter delivers pending entries as system notifications via `osascript`. The email adapter reads SMTP credentials from `private/email.toml` and sends via SMTP. Both support dry-run mode for testing.

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
uv run nuself memory source ingest private/sources/my-note.md --tag notes
uv run nuself memory source ingest private/sources/ --tag archive
```

Imported document metadata is stored under `private/sources/documents/`, and stable chunks are stored under `private/sources/chunks/`.

Inspect imported sources:

```bash
uv run nuself memory source list
uv run nuself memory source show <source-id>
uv run nuself memory source chunks <source-id>
uv run nuself memory source search "durable citation"
```

Extract reviewable profile candidates from an imported source:

```bash
uv run nuself memory source extract <source-id>
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
uv run nuself memory source delete <source-id>
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
- [Agent instructions](AGENTS.md)

## Development Policy

NuSelf is in active early development. Interfaces are expected to move quickly. Do not preserve obsolete CLI commands, protocol fields, schemas, or Python APIs unless current docs explicitly require compatibility.

When functionality, commands, configuration, runtime behavior, or other user-visible behavior changes, update both [README.md](README.md) and [README.zh-CN.md](README.zh-CN.md) in the same change.
