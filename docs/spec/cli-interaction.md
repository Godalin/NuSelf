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

## Time Display Contract

- Internal timestamps are stored as timezone-aware ISO timestamps, normally UTC.
- Filenames and machine-readable JSON output keep stable internal timestamps.
- Human-readable CLI, REPL, and transcript output renders timestamps in the current system timezone using second precision and an explicit UTC offset.
- Invalid or legacy timestamp strings are printed unchanged rather than failing the command.

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
- Chat turns print one leading blank line, then activity logs in chronological order, then one blank line and a `NuSelf:` label before the assistant reply. This keeps the final user-facing reply at the end of the turn so users can skip internal process output when they are not interested. The session header follows the reply without extra blank spacer lines.
- Interactive chat transport failures, including daemon timeouts, do not exit the REPL. The REPL captures and prints any logs produced before the failure, retries the same user message once, and then returns to the prompt if the retry also fails.
- A REPL retry is the same logical chat turn, not a second user turn. The client must reuse the same `turn_id` for every attempt of one user input. The daemon/chat layer must treat a completed `turn_id` as idempotent: if the first attempt completed after the client timed out, a retry returns the already-saved assistant reply instead of appending the same user message again or rerunning persona work.
- `:restart` and `:r` restart the daemon from inside the current REPL, then reconnect future requests to the restarted daemon. The command preserves the current thread and interactive transcript session. Restart failures print a concise error and keep the REPL open.
- Session header reprinted after non-command turns and thread-switching commands:
  ```
  [daemon] session status=<running|one-shot> thread=<id>
  ```
- NuSelf assistant replies printed to an interactive terminal are rendered as Markdown.
- Terminal assistant replies are streamed with a small typewriter effect so the reply appears progressively. The plain stored transcript remains unchanged.
- Structured response JSON is an internal transport protocol. The user-facing assistant reply must contain only the `answer` text, never the raw JSON object, fenced protocol block, or protocol field names. If a generated reply leaks the response protocol into the user-visible answer, the chat agent should ask the model to regenerate once with the same context and stricter user-facing-output instruction, rather than mechanically editing the bad answer.

### Activity Printing

During each chat turn, before printing the assistant reply, the REPL polls for and prints new log events as they are written using `render_log_event()`. It does not wait for the final assistant reply before showing internal progress logs.

All human-readable logs use one metadata style: `[component] event key=value ...`. Standard event fields and displayable metadata fields must use this same `key=value` style; they must not mix colon labels, raw JSON blocks, or ad hoc Markdown fields. If a log has body text, render that text starting on the next indented line instead of mixing it into the key/value header.

When a log records one subsystem calling another subsystem's service/tool boundary, it renders two leading tags: `[caller] [service] event key=value ...`. For example, chat calling a memory tool renders `[chat] [memory] service_tool_called ...`. The second tag comes from `metadata.service_component`; it is not repeated as `service_component=...` in the key/value header.

`persona_summary` activity is rendered as a multi-line block. The header follows the same `[component] event key=value ...` rule and names the event once, then each persona contribution is printed on its own indented line in contribution order, followed by the synthesizer line if present. It must not collapse multiple persona thoughts into one pipe-delimited line. Because self activation `status` and host `escalation_reason` values can be long natural-language text, `[selves]` logs render these values as indented body text instead of placing them in the header. Indented lines under `[selves]` logs are prose/body lines, not additional `key=value` metadata. If the log message already contains the escalation reason, the renderer must not repeat it as a separate `escalation_reason=...` field.

Competitive persona discussion logs, including chat-triggered and reflection-triggered discussions, are `persona` component logs and render with the display tag `[selves]`. Logs with `discussion_trace` metadata render the header as one compact log line and then print the trace underneath using the discussion trace block format. The trace block is indented relative to the log header so each self contribution reads like a chat message instead of a single serialized metadata list. Chat-triggered competitive discussions also emit `persona_discussion_step` logs as each trace entry is produced, then emit a final `persona_discussion` summary without re-dumping the full trace.

When color is enabled, each known self label in a `persona_summary` or `discussion_trace` block uses a stable distinct color. Color applies only to the speaker label, not the thought text, and no-color mode preserves the same plain text without ANSI escapes.

### Transcript Export

- Command: `:export` or `:e` writes a user-readable Markdown transcript for the current thread and copies the saved content to the system clipboard by default.
- Options may be combined in any order:
  - `all`: include all logs captured during this interactive connection.
  - `noclip`: save the file without copying to clipboard.
- Default log scope: chat transcript plus shareable internal logs (`chat/service_tool_called`, `persona_summary`, `host_discussion_decision`, `persona_discussion_step`, `persona_discussion`, and high-level reflection outcomes). Low-level daemon, memory, and chat completion logs are omitted unless `all` is used.
- Logs in transcript Markdown use the same human-readable rendering as interactive activity logs. Transcript logs must not expose raw JSON blocks.
- Transcript Markdown should be CommonMark-friendly: message bodies are fence-safe, log blocks render as Markdown blockquotes instead of consecutive raw code fences, headings are separated by blank lines, and the file ends with exactly one newline.
- Logs captured during a chat turn are inserted directly after the assistant message for that turn under a compact `### Logs` subheading. Export must preserve the observed interaction order instead of rendering all chat messages first and all logs later.
- Logs that cannot be associated with a specific chat turn are rendered at the end under `## Internal Process Logs`.
- Scope: transcript export starts at the current interactive connection time. Re-running export later in the same connection includes the full conversation and captured logs from that same connection start, not only messages/logs since the previous export.
- Exit commands (`:q`, `:quit`, `:exit`), EOF, and keyboard interrupt automatically save transcripts for every thread in the current interactive connection that has chat messages not already covered by a manual export. This automatic save does not copy to the clipboard.
- Storage: files are written under `private/transcripts/`.
- Filename: includes the connection start time and export command time, e.g. `chat-default-20260514T120000123456Z-20260514T121500654321Z.md`.
- Output: after saving, print the file path and clipboard copy result. If `noclip` is used, do not attempt clipboard copying.

## Command Model

v0.2.0 reorganizes the command tree around user-facing concepts. This is a breaking cleanup; old command paths are removed instead of kept as compatibility aliases.

Top-level commands:

| Command | Purpose |
|---|---|
| `nuself` | Open interactive chat by default |
| `nuself chat` | Explicit chat entry |
| `nuself attach` | Attach to a running daemon |
| `nuself daemon` | Background process lifecycle |
| `nuself thread` | Conversation thread management |
| `nuself memory` | Memory, sources, profile, review queue, graph |
| `nuself inbox` | User-facing proactive items: reflection and notifications |
| `nuself reason` | Long-run reasoning threads |
| `nuself trace` | Thought provenance records |
| `nuself dev` | Diagnostics, logs, config, health, eval, status |

Breaking moves:

| Removed path | New path |
|---|---|
| `nuself source ...` | `nuself memory source ...` |
| `nuself reflection ...` | `nuself inbox reflection ...` |
| `nuself notify ...` | `nuself inbox notify ...` |
| `nuself logs ...` | `nuself dev logs ...` |
| `nuself status` | `nuself dev status` or `nuself daemon status` |
| `nuself health` | `nuself dev health` |
| `nuself config` | `nuself dev config` |
| `nuself eval` | `nuself dev eval` |
| `nuself memory candidate ...` | `nuself memory review ...` |
| `nuself thread create ...` | `nuself thread new ...` |

Top-level help should group commands as:

- Daily: default chat, `chat`, `attach`
- Objects: `thread`, `memory`, `inbox`, `reason`, `trace`
- System: `daemon`, `dev`

REPL commands mirror the same model:

| Command | Purpose |
|---|---|
| `:inbox`, `:i` | List pending proactive items |
| `:inbox reflection ...` | Reflection commands |
| `:inbox notify ...` | Notification commands |
| `:mem`, `:m` | Memory preview |
| `:thread`, `:t` | Thread switching/listing |
| `:reason` | Long-run reasoning commands |
| `:trace` | Thought provenance commands |
| `:dev status` | Session/system status |
| `:restart`, `:r` | Restart daemon and reconnect |
| `:export`, `:e` | Transcript export |

## Command Group Reference

### Reflection

```
nuself inbox reflection list [--status pending|dismissed|archived] [--json]
```

- **Default view**: All reflection entries.
- **`--status`**: Filter to one entry status.
- **Output**: Indexed record blocks. First line contains metadata only, e.g. `[<N>] [reflection] status=[<status>] created=<timestamp> type=<candidate_type> score=<composite>`; second line contains the reflection title as indented body text. The component tag and status tag are colored when color is enabled.
- **ID display**: Plain-text list output does not print long `reflection-candidate-*` entry IDs. Use the visible index with `--by-index`, or use `--json` when the full ID is needed.
- **Empty**: `No reflection entries.`

```
nuself inbox reflection show <id_or_index> [--by-index] [--json]
```

- Indexes into the same filtered list used by `reflection list`.
- **Detail view**: One record header containing ID, status, candidate metadata, deep link, and timestamps; body text starts on the next indented line; discussion trace uses the indented discussion trace block.

```
nuself inbox reflection promote <id_or_index> [--by-index]
```

- Creates a reason thread from the selected reflection without dismissing or archiving the reflection.
- Writes trace provenance through the reason/reflection services.
- Output prints the created reason thread id and renders the reason detail view.

### Logs

```
nuself dev logs [--component <c>] [--tail N] [--json] [--no-color]
```

- **Purpose**: Raw audit trail. No semantic filtering.
- **Output**: `[component] event status=... duration_ms=... thread=... request=... error=...`, with body text on following indented lines when present.

### Notifications

```
nuself inbox notify list [--status <state>]
```

- **Output**: `<id> [<status>] <title> created=... attempts=... link=<true|false>`
- `--status` filters at the outbox level.

```
nuself inbox notify show <id>
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
4. Render the trace section title as a square-bracket tag, such as `[discussion]`.
5. Render each group header as a square-bracket tag, such as `[host]`, `[candidate]`, or `[turn-1]`.
6. If the group header and speaker are the same, render one tag followed by the content instead of repeating `[host] [host]` or `[candidate] [candidate]`.
