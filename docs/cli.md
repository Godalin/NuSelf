# CLI Guide

NuSelf is CLI-first. Run commands from the project root:

```bash
uv run nuself --help
uv run nuself <command> --help
```

Use `--project-root PATH` before the command to target another NuSelf project.
The examples below omit the `uv run` prefix only in explanatory text; commands
show the complete source-checkout invocation.

## Chat

The root command starts or connects to the daemon-backed interactive chat:

```bash
uv run nuself
uv run nuself --message "What should I revisit today?"
```

Run a chat turn without requiring a daemon:

```bash
uv run nuself chat
uv run nuself chat --message "Summarize what you know about this project."
```

Attach to an existing daemon session:

```bash
uv run nuself attach
uv run nuself attach --message "Continue."
```

## Daemon

```bash
uv run nuself daemon start
uv run nuself daemon status
uv run nuself daemon health
uv run nuself daemon attach
uv run nuself daemon restart
uv run nuself daemon stop
```

The daemon hosts chat plus background memory, reflection, reasoning, and
notification workers over a local Unix socket.

## Threads

```bash
uv run nuself thread list
uv run nuself thread new research
uv run nuself thread open research
uv run nuself thread branch research research-alt
uv run nuself thread archive research
uv run nuself thread archived
```

Add `--help` to a subcommand for ID/index options and destructive-operation
confirmation rules.

## Memory And Sources

```bash
uv run nuself memory list
uv run nuself memory search "retrieval"
uv run nuself memory preview
uv run nuself memory stats
uv run nuself memory review list
uv run nuself memory source list
uv run nuself memory profile list
uv run nuself memory graph search "project"
```

See [`memory.md`](memory.md) for the ingestion, review, and curation workflow.

## Reflections And Notifications

```bash
uv run nuself inbox reflection list
uv run nuself inbox reflection show <reflection-id>
uv run nuself inbox reflection dismiss <reflection-id>

uv run nuself inbox notify list
uv run nuself inbox notify show <notification-id>
uv run nuself inbox notify send <notification-id>
uv run nuself inbox notify dismiss <notification-id>
```

## Long-Run Reasoning And Trace

```bash
uv run nuself reason start "Plan the next project milestone"
uv run nuself reason list
uv run nuself reason show <reason-id>
uv run nuself reason advance <reason-id>
uv run nuself reason watch

uv run nuself trace list
uv run nuself trace search "project milestone"
```

Reason threads preserve sustained work; trace records expose thought
provenance.

## Thought Packs

```bash
uv run nuself pack export my-pack
uv run nuself pack inspect private/exports/my-pack.sqlite
uv run nuself pack import private/exports/my-pack.sqlite
```

Thought packs are SQLite snapshots for explicit export/import. They are not a
replacement for normal project authority or backup discipline.

## Diagnostics

```bash
uv run nuself dev status
uv run nuself dev health
uv run nuself dev config
uv run nuself dev storage
uv run nuself dev logs --component chat --tail 20
```

Migration and schema inspection are developer operations:

```bash
uv run nuself dev migrate
uv run nuself dev db-schema
```

Read their `--help` output before use. Migration is the only supported
file-to-SQLite authority switch.

## Discoverability

The CLI help is the current command reference:

```bash
uv run nuself --help
uv run nuself memory --help
uv run nuself memory source --help
```

The authoritative command, output, and REPL contracts are maintained in
[`spec/cli.md`](spec/cli.md). Errors and retry policy are documented in
[`spec/errors.md`](spec/errors.md).
