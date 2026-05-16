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
- Left-to-right: primary identifier when useful → colored status tag → human title → `key=value` metadata.
- Indexed only when `show` accepts a numeric index.

## Detail View Contract

- Detail views use the same record shape as lists and logs: one compact header followed by optional indented body text.
- Header shape: `<label> key=value ...`. The label may include the identifier, colored status tag, and title.
- Body or long text starts on the next line with two-space indentation. It must not be mixed into the header.
- Nested sub-structures, such as discussion traces, render under an indented section header using the same body indentation.
- Status fields use colored text in the label when color is enabled.

## Record Rendering Contract

Shared terminal renderers must use the reusable record helpers in `nuself.tui.render`:

- `render_record_header(label, fields)` joins the label and `key=value` metadata on one line.
- `render_record_body(text)` prints non-empty body lines with two-space indentation.
- `render_record_block(label, fields, body=...)` combines the two.
- `render_key_value_field(key, value)` is the common formatter for booleans, numbers, strings, lists, and structured fallback values.

Logs, `reflection list/show`, `notify list/show`, and REPL versions of those views must use this shared style. They must not reintroduce colon-aligned detail tables, raw JSON blobs, or one-off key/value renderers for human-readable output.

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

- Default interactive startup prints only the banner, one concise help line, and the session header. It must not also print daemon preamble or a separate tip line.
- Commands print one leading blank line before their output and do not add a trailing blank line before the next prompt or session header.
- Chat turns print one leading blank line, then a `NuSelf:` label before the assistant reply. Activity logs are separated from the reply by one blank line plus a compact `Logs:` label, and the session header follows the logs without extra blank spacer lines.
- Interactive chat transport failures, including daemon timeouts, do not exit the REPL. The REPL captures and prints any logs produced before the failure, retries the same user message once, and then returns to the prompt if the retry also fails.
- Session header reprinted after non-command turns and thread-switching commands:
  ```
  session thread=<id> daemon=<running|one-shot>
  ```
- NuSelf assistant replies printed to an interactive terminal are rendered as Markdown.
- Terminal assistant replies are streamed with a small typewriter effect so the reply appears progressively. The plain stored transcript remains unchanged.
- Structured response JSON is an internal transport protocol. The user-facing assistant reply must contain only the `answer` text, never the raw JSON object, fenced protocol block, or protocol field names. If a generated reply leaks the response protocol into the user-visible answer, the chat agent should ask the model to regenerate once with the same context and stricter user-facing-output instruction, rather than mechanically editing the bad answer.

### Activity Printing

After each chat turn, the REPL prints all new log events that occurred during that turn using `render_log_event()`.

All human-readable logs use one metadata style: `[component] event key=value ...`. Standard event fields and displayable metadata fields must use this same `key=value` style; they must not mix colon labels, raw JSON blocks, or ad hoc Markdown fields. If a log has body text, render that text starting on the next indented line instead of mixing it into the key/value header.

`persona_summary` activity is rendered as a multi-line block. The header follows the same `[component] event key=value ...` rule and names the event once, then each persona contribution is printed on its own indented line in contribution order, followed by the synthesizer line if present. It must not collapse multiple persona thoughts into one pipe-delimited line.

Logs with `discussion_trace` metadata, including chat and reflection `persona_discussion` events, render the header as one compact log line and then print the trace underneath using the discussion trace block format. The trace block is indented relative to the log header so each self contribution reads like a chat message instead of a single serialized metadata list.

When color is enabled, each known self label in a `persona_summary` block uses a stable distinct color. Color applies only to the speaker label, not the thought text, and no-color mode preserves the same plain text without ANSI escapes.

### Transcript Export

- Command: `:export` or `:e` writes a user-readable Markdown transcript for the current thread and copies the saved content to the system clipboard by default.
- Options may be combined in any order:
  - `all`: include all logs captured during this interactive connection.
  - `noclip`: save the file without copying to clipboard.
- Default log scope: chat transcript plus shareable internal logs (`persona_summary`, `host_discussion_decision`, `persona_discussion`, and high-level reflection outcomes). Low-level daemon, memory, and chat completion logs are omitted unless `all` is used.
- Logs in transcript Markdown use the same human-readable rendering as interactive activity logs. Transcript logs must not expose raw JSON blocks.
- Scope: transcript export starts at the current interactive connection time. Re-running export later in the same connection includes the full conversation and captured logs from that same connection start, not only messages/logs since the previous export.
- Exit commands (`:q`, `:quit`, `:exit`) and EOF automatically save transcripts for every thread in the current interactive connection that has chat messages not already covered by a manual export. This automatic save does not copy to the clipboard.
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
- **Output**: Indexed record blocks. First line contains metadata only, e.g. `[<N>] [reflection] status=[<status>] created=<timestamp> type=<candidate_type> score=<composite>`; second line contains the reflection title as indented body text. The component tag and status tag are colored when color is enabled.
- **ID display**: Plain-text list output does not print long `reflection-candidate-*` entry IDs. Use the visible index with `--by-index`, or use `--json` when the full ID is needed.
- **Empty**: `No reflection entries.`

```
nuself reflection show <id_or_index> [--by-index] [--json]
```

- Indexes into the same filtered list used by `reflection list`.
- **Detail view**: One record header containing ID, status, candidate metadata, deep link, and timestamps; body text starts on the next indented line; discussion trace uses the indented discussion trace block.

### Logs

```
nuself logs [--component <c>] [--tail N] [--json] [--no-color]
```

- **Purpose**: Raw audit trail. No semantic filtering.
- **Output**: `[component] event status=... duration_ms=... thread=... request=... error=...`, with body text on following indented lines when present.

### Notifications

```
nuself notify list [--status <state>]
```

- **Output**: `<id> [<status>] <title> created=... attempts=... link=<true|false>`
- `--status` filters at the outbox level.

```
nuself notify show <id>
```

- **Output**: One record header with ID, status, title, delivery metadata, and deep link; body text starts on the next indented line.

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
