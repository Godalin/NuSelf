# NuSelf

[中文说明](README.zh-CN.md)

NuSelf is a local-first AI mirror for deep personal discussion. It combines
resumable chat, private memory, long-running reasoning, proactive reflection,
and controlled notifications in a user-owned authority or an explicitly
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

- Memory-aware one-shot and daemon-backed chat
- Persisted, resumable, branchable conversation threads
- Durable memory with review, search, relations, and symbolic graph views
- Markdown and plain-text source ingestion with cited profile extraction
- Long-run reasoning threads and traceable thought provenance
- Background memory curation and proactive reflection
- Durable notification outbox with log, email, and macOS adapters
- Local SQLite authority, migration tooling, and portable thought packs
- Ordered model endpoints with OpenAI-compatible or Anthropic protocols
- Structured diagnostics with credential redaction

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

For an Anthropic Messages endpoint, add `anthropic: true`. NuSelf does not
guess provider protocol from a URL or model name.

Inspect the effective, credential-redacted configuration:

```bash
uv run nuself dev config
```

See the [configuration guide](docs/configuration.md) for failover, chat
context, reflection, daemon, and notification settings.

### 3. Start chatting

Start or connect to the local daemon-backed interactive session:

```bash
uv run nuself
```

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

### Resume a thread

```bash
uv run nuself thread list
uv run nuself thread open default
uv run nuself thread branch default alternative
```

### Search and curate memory

```bash
uv run nuself memory search "decision"
uv run nuself memory preview
uv run nuself memory update
uv run nuself memory review list
```

### Import personal notes

```bash
uv run nuself memory source ingest ~/notes.md --tag notes
uv run nuself memory source list
uv run nuself memory source extract <source-id>
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
uv run nuself data list memory
uv run nuself data show memory <memory-id>
uv run nuself data edit memory <memory-id>
uv run nuself data export threads --format json
```

Generic editing validates the complete record, shows a diff, confirms the
change, and rejects concurrent overwrites. Operational collections are hidden
unless `--internal` is explicit.

The [CLI guide](docs/cli.md) groups the available workflows; the CLI's
`--help` output is the current command reference.

## Privacy And Storage

Personal state defaults to `~/.nuself`. Use `--local` for `./.nuself` or
`--workspace PATH` for `PATH/.nuself`; each selection is an isolated state
authority. Workspace configuration inherits user defaults, but databases and
runtime state are never merged.

NuSelf is local-first, not model-offline: when you configure a remote model,
the context required for that call is sent to the endpoint you selected.
Choose providers and retention policies accordingly.

Important boundaries:

- The source checkout is not an implicit data root.
- Default tests and CI do not read private project data.
- Opt-in live API tests use fixed synthetic prompts.
- Diagnostic configuration output redacts credentials.
- Thought packs and JSON exports are explicit portability tools; keep separate
  backups of the selected authority.

See the [memory guide](docs/memory.md) and
[storage specification](docs/spec/storage-v2.md) for details.

## Current Limitations

- NuSelf is an early CLI-first system, not a polished desktop application.
- Model quality and tool support vary by provider and selected model.
- Background curation, reflection, and delivery require the daemon.
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
- [Current development goal](docs/current-goal.md)
- [TODOs](docs/TODOs.md)

Behavioral contracts belong in `docs/spec/`; completed release history belongs
in `CHANGELOG.md`. The README intentionally stays a concise project entry
point.
