# NuSelf

[中文说明](README.zh-CN.md)

NuSelf is a local-first AI mirror for deep personal discussion. It combines
resumable chat, private memory, long-running reasoning, proactive reflection,
and controlled Inbox delivery in a user-owned authority or an explicitly
selected workspace.

NuSelf is CLI-first and designed for people who want to inspect and own their
agent's data rather than hide it behind a hosted account.

## Status

The current stable release is **v0.3.1**, with installed user-scoped storage
and explicit isolated workspaces.

NuSelf is in active development. The v0.3 line establishes the runtime,
storage, agent, and background-task foundations; interfaces may still change
aggressively in later development versions.

Supported platforms:

- Linux and macOS
- Python 3.12, 3.13, or 3.14
- Local source checkout managed with `uv`

Windows is not currently supported because runtime coordination uses POSIX
locks and Unix-domain sockets.

## Features

- Memory-aware chat with approved durable writes and local/UTC time access
- Persisted, resumable, branchable conversations
- Durable memory with review, search, relations, and symbolic graph views
- Independent Markdown and plain-text external knowledge library
- Long-run reasoning threads and traceable thought provenance
- API-separated conversation history, memory observations, and top-level reflection controls
- Unified Inbox with log, email, and macOS delivery of complete reflection text
- Local SQLite authority, migration tooling, and portable thought packs
- Transient retry plus ordered OpenAI-compatible/Anthropic endpoint failover
- Structured diagnostics with credential redaction
- Invocation-bound typed Tool effects (approval, observation, and audit) with generic suspension transport, plus one bounded daemon scheduler with
  recoverable maintenance wake-ups and resource-lane serialization

## Quick Start

### 1. Install

Clone the repository and create the locked environment:

```bash
git clone https://github.com/Godalin/NuSelf.git
cd NuSelf
uv sync --locked
```

Confirm the CLI:

```bash
uv run nuself --version
uv run nuself --help
```

Commands that need personal state require an explicit `nuself init`. If the
selected authority or model configuration is not ready, NuSelf prints the
exact next command and exits instead of starting a daemon or waiting at an
unusable prompt. Temporary chat transport failures keep an existing REPL open;
use `:retry` to retry the same logical turn safely.

### 2. Configure a model

Initialize the default user authority and copy the example configuration:

```bash
uv run nuself init
cp examples/.nuself/config.yaml ~/.nuself/config.yaml
```

For an OpenAI-compatible endpoint, edit `~/.nuself/config.yaml`:

```yaml
llm:
  - base_url: https://api.openai.com/v1
    api_key: YOUR_API_KEY
    model: gpt-4.1-mini
    timeout_seconds: 60
```

For an Anthropic Messages endpoint, add `anthropic: true`. NuSelf does not guess
provider protocol; the runtime accepts only the current schema, so migrate obsolete v0.2.5 fields before startup.

Inspect the effective, credential-redacted configuration:

```bash
uv run nuself dev config
```

See the [configuration guide](docs/configuration.md) for failover, chat
context, reflection, daemon, Inbox, and delivery settings.

### 3. Start chatting

Start or connect to the local daemon-backed interactive session:

```bash
uv run nuself
```

Opening another interactive client remains responsive while the daemon is
still completing a turn; startup reads the last committed conversation snapshot.
Ctrl-C cancels an in-flight turn only after its request transport is closed;
Ctrl-D exits through transcript, curator, and storage cleanup.

Send one message:

```bash
uv run nuself --message "Help me think through my current priorities."
```

Run chat without requiring a daemon:

```bash
uv run nuself chat --message "What do you know about this project?"
```

If no model is configured, NuSelf returns local configuration guidance rather
than pretending to produce a model-backed answer.

## Common Workflows

### Resume a conversation

```bash
uv run nuself conversation list
uv run nuself conversation open default
uv run nuself conversation branch default alternative
```

### Search and curate memory

```bash
uv run nuself memory search "decision"
uv run nuself memory preview
uv run nuself memory update
```

### Import personal notes

```bash
uv run nuself source ingest ~/notes.md --tag notes
uv run nuself source list
```

### Continue a long-running question

```bash
uv run nuself reason start "What should I focus on next?"
uv run nuself reason list
uv run nuself reason advance <reason-id>
```

### Inspect runtime health

```bash
uv run nuself daemon status
uv run nuself dev health
uv run nuself dev logs --component chat --tail 20
```

### Inspect or edit stored data

```bash
uv run nuself data collections
uv run nuself data check memory
uv run nuself data list memory
uv run nuself data show memory <memory-id>
uv run nuself data edit memory <memory-id>
uv run nuself data export threads --format json
```

`data check` finds invalid records without changing them and prints the exact
`edit` or confirmed `delete` command for each one. One-time legacy migrations
live under `scripts/`; the installed CLI carries none. Generic editing validates
full records and rejects concurrent overwrites.

Schema v5 keeps domain records and namespaced workspace state in one compact
authority database without redundant indexes. Upgrades remain explicit and
reversible; see the
[migration specification](docs/spec/database-migrations.md).

The [CLI guide](docs/cli.md) groups the available workflows; the CLI's
`--help` output is the current command reference.

## Privacy And Storage

Personal state defaults to `~/.nuself`. Use `--local` for `./.nuself` or
`--workspace PATH` for `PATH/.nuself`; each selection is an isolated state
authority. Workspace configuration inherits user defaults, but databases and
runtime state are never merged. Each authority permits exactly one NuSelf
daemon operating-system process; one bounded scheduler inside it coordinates
chat and background tasks.

Interactive chat shows a concise `Attention:` block when the selected
authority has no usable model, a local workspace authority was not selected,
persisted records cannot be decoded, or the daemon recently failed to deliver
a reply. Notices point to `data check` for repairable records and `:history`
for already-persisted chat replies; a successful record repair resolves its
older decode notices, and recurring delivery failures suggest a daemon restart.

NuSelf is local-first, not model-offline: when you configure a remote model,
the context required for that call is sent to the endpoint you selected.
Choose providers and retention policies accordingly.

Important boundaries:

- The source checkout is not an implicit data root.
- Default tests and CI do not read private project data.
- Opt-in live API tests use fixed synthetic prompts.
- Diagnostic configuration output redacts credentials.
- Observed tool activity logs include structured arguments and results by default; explicitly compact tools record only operation and status.
- Thought packs and JSON exports are explicit portability tools; keep separate backups of the selected authority.

See the [memory guide](docs/memory.md) and
[storage specification](docs/spec/storage-v2.md) for details.

## Current Limitations

- NuSelf is an early CLI-first system, not a polished desktop application.
- Model quality and tool support vary by provider and selected model.
- Background curation, reflection, and delivery require the daemon; chat replies do not wait for memory curation.
- macOS notifications are platform-specific; email requires explicit SMTP
  configuration.
- Windows is unsupported.
- Workspace scope must be selected explicitly; NuSelf does not automatically
  discover parent workspaces.

## Documentation

- [Configuration guide](docs/configuration.md)
- [CLI guide](docs/cli.md)
- [Memory guide](docs/memory.md)
- [Architecture](docs/architecture.md)
- [Behavioral specifications](docs/spec/README.md)
- [Test suite](tests/README.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

Behavioral contracts belong in `docs/spec/`; completed release history belongs
in `CHANGELOG.md`. This README intentionally stays a concise project entry point.
