# NuSelf

[中文版 README](README.zh-CN.md)

NuSelf is a local AI mirror project. It is intended to grow into a personal agent with private memory, resumable conversations, lightweight thought-personas, proactive reflection, and controlled notifications.

The current implementation is an early CLI-first skeleton:

- Local `nuself` command.
- Optional local background daemon over a Unix socket.
- A temporary memory-aware chat agent that can run one-shot or through the daemon.
- File-backed memory entries that can be listed, viewed, added, edited, deleted, searched, and re-indexed.
- Persisted chat threads with compressed conversation context.

LangGraph/LangChain integration, proactive reflection, email, and macOS notifications are planned but not implemented yet.

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

Without `--message`, `chat` and `attach` enter interactive mode. When terminal support is available, line editing and arrow-key history are backed by `private/runtime/interactive_history`. Input starting with `:` is treated as an interactive command. Type `:q`, `:quit`, `:exit`, or send EOF to leave; unknown commands print interactive help and keep the session open.

Current chat uses a temporary agent that loads memory entries from `private/memory/entries/`, appends turns to `private/threads/default.json`, and compresses older context into a thread summary once the conversation grows.

Context compression can be tuned in `.env`:

```text
NUSELF_CONTEXT_RECENT_MESSAGES=12
NUSELF_CONTEXT_SUMMARY_TRIGGER_MESSAGES=18
NUSELF_CONTEXT_SUMMARY_TARGET_CHARS=2400
```

The real mirror graph will replace this temporary runtime later.

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

Without a subcommand, `daemon` shows daemon subcommand help.

Daemon runtime files are stored under:

```text
private/runtime/
private/logs/
```

The first protocol is JSON lines over a Unix domain socket at `private/runtime/nuself.sock`.

## Memory Entries

Memory is managed as clear entries under:

```text
private/memory/entries/
```

Add an entry:

```bash
uv run nuself memory add \
  --type belief \
  --title "Clarity matters" \
  --body "Prefer explicit assumptions and source-aware reasoning." \
  --tag style
```

List entries:

```bash
uv run nuself memory list
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

Delete an entry:

```bash
uv run nuself memory delete <entry-id>
```

Rebuild the derived memory index:

```bash
uv run nuself memory reindex
```

The derived index is written to:

```text
private/derived/memory_index.json
```

## Memory Entry Types

Supported entry types:

- `source_note`
- `profile_fact`
- `belief`
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
