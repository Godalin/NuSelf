# CLI & Interaction Spec

## Design Principles

1. **Consistency**: The same concept looks similar across `list`, `show`, REPL, and logs.
2. **Lists are summaries, shows are details**: `list` prints one compact line per item. `show` prints a labeled multi-line block.
3. **Empty state is success**: `"No items."` → stdout, exit `0`. Not-found → stderr, exit `1`.
4. **Errors to stderr, success to stdout**.
5. **Color is informative, not required**: Degrades via `--no-color` or `NO_COLOR`.
6. **JSON mode is a first-class view**: Structured-data commands support `--json`.
7. **Separate user outcomes from internal audit**: `list` shows meaningful outcomes. `logs` shows the full audit trail.

## Color System

Controlled by `TerminalTheme`. Default ON when `sys.stdout.isatty()` and `NO_COLOR` is not set.

**Component tag colors:**

| Component | ANSI |
|---|---|
| `daemon` | `90` (gray) |
| `chat` | `34` (blue) |
| `memory` | `32` (green) |
| `persona` | `35` (magenta) |
| `outbox` | `36` (cyan) |
| `reflection` | `33` (yellow) |

**Semantic status colors:**

| State | Color |
|---|---|
| `approved`, `sent`, `accepted`, `reviewed` | green (`32`) |
| `rejected`, `failed`, `error` | red (`31`) |
| `pending`, `started`, `draft` | yellow (`33`) |
| `dismissed`, `skipped` | gray (`90`) |

## List View Contract

- One line per item.
- Left-to-right: primary identifier → colored status tag → human title → muted metadata.
- Indexed only when `show` accepts a numeric index.

## Detail View Contract

- Labeled fields aligned on the first colon: `label: value`.
- Status fields use colored text.
- Body or long text appears after a blank line.
- Sub-structures grouped under section headers with a blank line before the header.

## Empty State Contract

| Context | Output | Stream | Exit Code |
|---|---|---|---|
| `list` with no items | `No <items>.` | stdout | `0` |
| `show` with invalid ID | `<Item> not found: <id>` | stderr | `1` |
| `search` with no matches | `No matching <items>.` | stdout | `0` |
| `delete` with invalid ID | `<Item> not found: <id>` | stderr | `1` |

## JSON Mode Contract

- Flag: `--json` (or `--as-json` where parser conflicts require it).
- Lists print one JSON object per line (JSONL).
- Single-item `show` prints one JSON object.
- Disables color automatically.
- Uses `sort_keys=True, ensure_ascii=True`.

## REPL Conventions

### Command Prefix

All interactive commands start with `:`.

### Output Formatting

- Commands wrap output with leading and trailing blank lines.
- Session header reprinted after non-command turns and thread-switching commands:
  ```
  session thread=<id> daemon=<running|one-shot>
  ```
- NuSelf assistant replies printed to an interactive terminal are rendered as Markdown.
- Terminal assistant replies are streamed with a small typewriter effect so the reply appears progressively. The plain stored transcript remains unchanged.

### Activity Printing

After each chat turn, the REPL prints all new log events that occurred during that turn using `render_log_event()`.

`persona_summary` activity is rendered as a multi-line block. The header names the event once, then each persona contribution is printed on its own indented line in contribution order, followed by the synthesizer line if present. It must not collapse multiple persona thoughts into one pipe-delimited line.

When color is enabled, each known self label in a `persona_summary` block uses a stable distinct color. Color applies only to the speaker label, not the thought text, and no-color mode preserves the same plain text without ANSI escapes.

### Transcript Export

- Command: `:export` or `:e` writes a user-readable Markdown transcript for the current thread and copies the saved content to the system clipboard by default.
- Options may be combined in any order:
  - `all`: include all logs captured during this interactive connection.
  - `noclip`: save the file without copying to clipboard.
- Default log scope: chat transcript plus shareable internal logs (`persona_summary`, `host_discussion_decision`, `persona_discussion`, and high-level reflection outcomes). Low-level daemon, memory, and chat completion logs are omitted unless `all` is used.
- Scope: transcript export starts at the current interactive connection time. Re-running export later in the same connection includes the full conversation and captured logs from that same connection start, not only messages/logs since the previous export.
- Storage: files are written under `private/transcripts/`.
- Filename: includes the connection start time and export command time, e.g. `chat-default-20260514T120000123456Z-20260514T121500654321Z.md`.
- Output: after saving, print the file path and clipboard copy result. If `noclip` is used, do not attempt clipboard copying.

## Command Group Reference

### Reflection

```
nuself reflection list [--status pending|dismissed|archived] [--json]
```

- **Default view**: All reflection entries.
- **`--status`**: Filter to one entry status.
- **Output**: Indexed compact lines `[  N] [<status>] <title>  created=<timestamp>  type=<candidate_type>  score=<composite>`.
- **ID display**: Plain-text list output does not print long `reflection-candidate-*` entry IDs. Use the visible index with `--by-index`, or use `--json` when the full ID is needed.
- **Empty**: `No reflection entries.`

```
nuself reflection show <id_or_index> [--by-index] [--json]
```

- Indexes into the same filtered list used by `reflection list`.
- **Detail view**: ID, title, status, candidate metadata, deep link, timestamps, body, and raw discussion trace.

### Logs

```
nuself logs [--component <c>] [--tail N] [--json] [--no-color]
```

- **Purpose**: Raw audit trail. No semantic filtering.
- **Output**: `[component_tag] message status=... duration=...ms thread=... request=... error=...`

### Notifications

```
nuself notify list [--status <state>]
```

- **Output**: `<id> [<status>] title created=... attempts=... link|-`
- `--status` filters at the outbox level.

```
nuself notify show <id>
```

- **Output**: Labeled multi-line block with body.

### Daemon

```
nuself daemon start | stop | restart | status | list
```

- **Output**: Plain text state lines (`daemon running pid=... socket=...`).
- **Error**: State mismatch printed to stderr with exit code `1`.

### Memory

All memory subcommands follow the same list/detail/empty/error contracts.

- **List**: `[mem] <state_color>reviewed</> <type> <id> Title #tags conf=...`
- **Detail**: Header + metadata + tags + evidence + wrapped body.

## Discussion Trace Contract

Discussion traces rendered by `render_discussion_trace()` must:

1. Group entries by turn (`candidate`, `host`, `turn-N`).
2. Prefix each speaker utterance with `[speaker]` aligned to 18 columns.
3. Separate turns with a blank line.
4. Use `── turn-label ──` as turn headers.
