# CLI Guide

NuSelf is CLI-first. Installed commands may run from any directory:

```bash
uv run nuself --help
uv run nuself <command> --help
```

The default authority is `~/.nuself`. Use `--local` for `./.nuself` or
`--workspace PATH` for `PATH/.nuself`; both flags precede the command and are
mutually exclusive. NuSelf never switches scope merely because the current
directory contains `.nuself`.
The examples below omit the `uv run` prefix only in explanatory text; commands
show the complete source-checkout invocation.

## Authorities And Migration

```bash
uv run nuself init
uv run nuself --local init
uv run nuself --workspace /path/to/workspace init
uv run nuself dev paths
```

Legacy v0.3.0 checkout-local state is migrated only by an explicit command.
The source is validated and preserved, and an existing target is never merged
or overwritten:

```bash
uv run nuself migrate-layout --from ./private --to user
uv run nuself migrate-layout --from ./private --to-local
uv run nuself migrate-layout --from ./private --workspace /path/to/workspace
```

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

## Data Inspection And Editing

```bash
uv run nuself data collections
uv run nuself data check memory
uv run nuself data list memory
uv run nuself data show threads default
uv run nuself data export memory --format json --output memory.json
uv run nuself data edit memory <memory-id>
uv run nuself data delete threads <thread-id>
```

List, show, and export cover all public structured collections. `data check`
uses the domain validator without mutation, returns failure when invalid
records exist, and prints an `edit` and confirmed `delete` command for every
invalid stable ID. Generic edit and delete are limited to domain-validated
memory and chat-thread records; other domains use their dedicated commands.
Mutation shows a diff or destructive prompt unless `--yes` is explicit. Add
`--internal` only when diagnosing hidden curator or scheduler state.

One-time record migrations are repository scripts rather than installed CLI
commands. Preview with
`uv run python scripts/migrate_legacy_memory_records.py --authority-root .nuself`
and add `--apply` explicitly to commit. Unknown legacy data stays untouched.

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
uv run nuself pack inspect ~/.nuself/exports/my-pack.sqlite
uv run nuself pack import ~/.nuself/exports/my-pack.sqlite
```

Thought packs are SQLite snapshots for explicit export/import. They are not a
replacement for normal project authority or backup discipline.

## Diagnostics

```bash
uv run nuself dev status
uv run nuself dev health
uv run nuself dev config
uv run nuself dev paths
uv run nuself dev storage
uv run nuself dev logs --component chat --tail 20
```

Schema inspection is a developer operation:

```bash
uv run nuself dev db-schema
```

Use `nuself migrate-layout` for an explicit legacy directory move. It accepts
only a valid SQLite authority; file-backed collection migration is retired.

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
