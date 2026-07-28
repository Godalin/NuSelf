# CLI & Interaction Spec

## Design Principles

1. **Consistency**: The same concept looks similar across `list`, `show`, REPL, and logs.
2. **Lists are summaries, shows are details**: `list` prints one compact line per item. `show` prints a labeled multi-line block.
3. **Empty state is success**: `"No items."` → stdout, exit `0`. Not-found → stderr, exit `1`.
4. **Errors to stderr, success to stdout**.
5. **Color is informative, not required**: Degrades via `--no-color` or `NO_COLOR`.
6. **JSON mode is a first-class view**: Structured-data commands support `--json`.
7. **Separate user outcomes from internal audit**: `list` shows meaningful outcomes. `logs` shows the full audit trail.

## Exception Presentation

Every caught exception rendered by `nuself.cli` uses the shared safe diagnostic
message formatter. This applies equally to stderr, recoverable REPL text,
transcript/export status, and auxiliary audit `error` fields. A broken
exception renderer falls back to its class name, and credential-like values are
removed before presentation.

Stable strings already decoded from a daemon error response are protocol-owned
user outcomes and are not reinterpreted as exception objects. Sanitization does
not change exit codes, retry metadata, stdout/stderr routing, command ownership,
or whether an exception is caught versus propagated.

## Color System

Controlled by `TerminalTheme`. Default ON when `sys.stdout.isatty()` and `NO_COLOR` is not set.

**Component tag colors:**

| Component    | ANSI           |
| ------------ | -------------- |
| `daemon`     | `90` (gray)    |
| `chat`       | `34` (blue)    |
| `memory`     | `32` (green)   |
| `persona`    | `35` (magenta) |
| `outbox`     | `36` (cyan)    |
| `reflection` | `33` (yellow)  |

**Semantic status colors:**

| State                                      | Color         |
| ------------------------------------------ | ------------- |
| `approved`, `sent`, `accepted`, `reviewed` | green (`32`)  |
| `rejected`, `failed`, `error`              | red (`31`)    |
| `pending`, `started`, `draft`              | yellow (`33`) |
| `dismissed`, `skipped`                     | gray (`90`)   |

## List View Contract

- One record block per item.
- Header line: subsystem tag → visible index when present → colored status field when present → `key=value` metadata.
- Body lines: human-readable title, summary, or long text start on the next line with two-space indentation. Long text must not be mixed into the header.
- Human-readable object lists use temporary visible indexes when the object can be inspected or acted on later. Indexes are **0-based** and render as a square-bracket tag (`[0]`, `[1]`, ...), after the subsystem tag.
- Key/value fields may colorize values for scanability when color is enabled. Stable IDs, paths, and tags should be muted; status and object type values may use subsystem-specific colors. No-color output must remain plain `key=value` text.
- Commands that accept an object handle resolve a compact numeric argument as the visible 0-based index from the corresponding default list view; nonnumeric arguments are stable IDs. JSON output keeps stable IDs and does not need visible indexes.
- Commands that explicitly support batch index selections accept a compact expression with comma-separated indexes and inclusive ranges, e.g. `1,3-5,9`. Whitespace inside the expression is invalid. The compact expression itself implies index lookup. Stable IDs that carry subsystem prefixes such as `mem_` do not conflict with this grammar.
- CLI-visible handle parsing is shared infrastructure. Command handlers, repositories, and services that accept visible indexes must use `nuself.handles` rather than duplicating index/range parsing locally.

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

Logs, `memory list/show`, `reflection list/show`, `notify list/show`, and REPL versions of those views must use this shared style. They must not reintroduce colon-aligned detail tables, raw JSON blobs, or one-off key/value renderers for human-readable output.

## Time Display Contract

- Internal timestamps are stored as timezone-aware ISO timestamps, normally UTC.
- Filenames and machine-readable JSON output keep stable internal timestamps.
- Human-readable CLI, REPL, and transcript output renders timestamps in the current system timezone using second precision and an explicit UTC offset.
- Invalid or legacy timestamp strings are printed unchanged rather than failing the command.

## Empty State Contract

| Context                  | Output                   | Stream | Exit Code |
| ------------------------ | ------------------------ | ------ | --------- |
| `list` with no items     | `No <items>.`            | stdout | `0`       |
| `show` with invalid ID   | `<Item> not found: <id>` | stderr | `1`       |
| `search` with no matches | `No matching <items>.`   | stdout | `0`       |
| `delete` with invalid ID | `<Item> not found: <id>` | stderr | `1`       |

## JSON Mode Contract

- Flag: `--json` (or `--as-json` where parser conflicts require it).
- Lists print one JSON object per line (JSONL).
- Single-item `show` prints one JSON object.
- Disables color automatically.
- Uses `sort_keys=True, ensure_ascii=True`.

## REPL Conventions

### Session State Ownership

Each `run_interactive_loop()` call owns one `InteractiveSession` and one
interactive input state.

- History and completion objects are created for that loop's project root and
  are never stored in mutable module globals.
- Consecutive history de-duplication and the existing history file path remain
  unchanged.
- `:history` reports the existing empty-history message when a thread is absent
  or has no messages. A malformed or unreadable persisted thread instead
  renders a concise load-failure message with the compact exception chain; it
  must not be presented as an empty thread.
- Session headers are presentation effects, not persisted session state.
- Non-TTY sessions use built-in `input()` without a degradation event. Terminal
  capability `AttributeError` and terminal/prompt `OSError` failures emit one
  payload-safe `chat/interactive_prompt_failed` warning through the shared
  best-effort boundary, then use built-in input. Unexpected prompt failures,
  `EOFError`, and `KeyboardInterrupt` are not fallback conditions and
  propagate.
- Dynamic thread/reason completion and persisted input history are optional UI
  effects. Their failure yields no storage-backed suggestions or skips the
  history write, but never rejects an already accepted input line. Each failure
  is reported through the shared observable best-effort boundary; local broad
  exception suppression is not allowed.
- Tests and embedded callers may construct two sessions in one process without
  requiring a global reset hook.
- Every exit path runs transcript auto-save and exit memory curation exactly
  once, in that order. EOF does not perform an additional inline save.
- Both cleanup steps are attempted even if the first fails. Cleanup failures
  are never converted into a successful exit code.

### Command Prefix

All interactive commands start with `:`.

Top-level REPL command names, aliases, one-line descriptions, and detailed help
lines have one authoritative registry in `nuself.cli.repl.registry`. Command
matching, completion, unknown-command suggestions, and `:help` render from that
registry. Subsystem-specific argument parsing may remain with its handler, but
must resolve the top-level command through the registry instead of repeating
alias string sets.

### Output Formatting

- Default interactive startup prints only the banner, one concise help line, and the session header. It must not also print daemon preamble or a separate tip line.
- Commands print one leading blank line before their output and do not add a trailing blank line before the next prompt or session header.
- Chat turns print one leading blank line, then activity logs in chronological order, then one blank line and a `NuSelf:` label before the assistant reply. This keeps the final user-facing reply at the end of the turn so users can skip internal process output when they are not interested. The session header follows the reply without extra blank spacer lines.
- Interactive chat transport failures, including daemon timeouts, do not exit the REPL. The REPL captures and prints any logs produced before the failure, retries the same user message once, and then returns to the prompt if the retry also fails.
- The daemon client supplies the transport failure's structural retry decision.
  Local request-encoding failures and malformed typed payloads from a valid
  response envelope are not retried; retry policy never parses exception text.
  The interactive result retains the failure phase, daemon request id, and
  possible-completion flag, and `turn_retry` records them in metadata.
- A REPL retry is the same logical chat turn, not a second user turn. The client must reuse the same `turn_id` for every attempt of one user input. The daemon/chat layer must treat a completed `turn_id` as idempotent: if the first attempt completed after the client timed out, a retry returns the already-saved assistant reply instead of appending the same user message again or rerunning persona work.
- Daemon/one-shot completion and failure records, curator status records, and
  the `turn_retry` marker are auxiliary projections through the shared
  best-effort observability boundary. Their failure, including an uncertain
  `LogAppendLifecycleError`, cannot replace a completed reply, convert an
  application result, or suppress/trigger a transport retry. Only the typed
  daemon connection result controls retry.
- `:restart` and `:r` restart the daemon from inside the current REPL, then reconnect future requests to the restarted daemon. The command preserves the current thread and interactive transcript session. Restart failures print a concise error and keep the REPL open.
- The session header is printed once at startup, once after every completed
  non-command turn (including a failed turn returning to the prompt), and once
  after commands whose dispatcher result is `redraw_header`. Other commands do
  not print it. All three paths use the same presenter and status provider:
  ```
  [daemon] session status=<running|one-shot> thread=<id>
  ```
- NuSelf assistant replies printed to an interactive terminal are rendered as Markdown.
- Terminal assistant replies are streamed with a small typewriter effect so the reply appears progressively. The plain stored transcript remains unchanged.
- Structured response JSON is an internal transport protocol. The user-facing assistant reply must contain only the `answer` text, never the raw JSON object, fenced protocol block, or protocol field names. If a generated reply leaks the response protocol into the user-visible answer, the chat agent should ask the model to regenerate once with the same context and stricter user-facing-output instruction, rather than mechanically editing the bad answer.

### Activity Printing

During each chat turn, before printing the assistant reply, the REPL polls for new log events as they are written and prints only interactive activity logs using `render_log_event()`. It does not wait for the final assistant reply before showing current-turn progress logs. Live REPL activity must be scoped to the current top-level `turn_id`; timestamp order alone is not enough to decide that a log belongs to the visible turn.

Interactive activity logs are user-relevant events from the current chat path: direct chat service/tool calls, approval prompts for gated tool execution, persona/self discussion progress, and chat/daemon failure or failover events. Background subsystem logs from reason, reflection, memory, trace, notification, or other autonomous services must not appear in the live REPL output only because they were written while a chat turn was waiting. They remain available through `nuself dev logs` and subsystem commands.

The interactive session captures the current chat path's `chat`, `daemon`, and
`persona` activity plus approval prompts for transcript export. `:export all`
includes every such captured event, including low-level ones that live output
and the default shareable export omit; it does not turn reason, reflection,
memory, trace, notification, or other concurrent background audit records into
chat-transcript activity.

When attached to the daemon, the REPL opens a turn-scoped activity
subscription and long-polls bounded event batches while the chat request runs.
It closes the subscription after draining the final batch. Local one-shot mode
uses the incremental file cursor because producer and consumer share one
process. Daemon-attached live output must not discover events by polling log
files.

If daemon activity open, poll, or final drain fails, the REPL reports one
structured degradation event and switches to the same turn-scoped incremental
cursor used by local mode. Subscription close failure is also observed but
does not alter chat success. These failures never trigger a chat retry by
themselves.

All human-readable logs use one metadata style: `[component] event key=value ...`. Standard event fields and displayable metadata fields must use this same `key=value` style; they must not mix colon labels, raw JSON blocks, or ad hoc Markdown fields. If a log has body text, render that text starting on the next indented line instead of mixing it into the key/value header.

When a log records one subsystem calling another subsystem's service/tool boundary, it renders two leading tags: `[caller] [service] event key=value ...`. For example, chat calling a memory tool renders `[chat] [memory] service_tool_called ...`. The second tag comes from `metadata.service_component`; it is not repeated as `service_component=...` in the key/value header.

Persona audit activity renders with the display tag `[selves]` and the shared
compact `key=value` header. These audit records are deliberately content-free:
`persona_summary` carries only contribution count and synthesis presence;
`host_discussion_decision` carries only the escalation boolean; and
`persona_discussion_step` carries only its ordinal. Persona contributions,
synthesis, escalation reasons, and discussion utterances remain in the
authoritative persona result/trace rather than being copied into Chat logs or
transcript audit blocks. The final `persona_discussion` record contains stable
ids, outcome booleans, and counts only.

The live-chat send thread is a continuation of the interactive turn, not an
independent worker. Its target captures the creating RuntimeContext before the
thread starts and restores the thread's prior context after completion or
failure. Long-lived daemon workers follow their separate runtime ownership
contract and never inherit CLI context.

An unexpected callback `Exception` becomes a non-retryable failed interactive
result after final activity drain and subscription close, and emits
`chat/interactive_send_failed`. A non-`Exception` `BaseException` such as
`KeyboardInterrupt` or `SystemExit` is process-control state: the main thread
skips auxiliary final drain, closes the subscription, and re-raises the same
exception object with its traceback. Control state must not be converted into
`code=1` or replaced by activity diagnostics.

The outer interactive lifecycle retains a main-loop `BaseException` while
running exit cleanup. If cleanup succeeds, it re-raises the same primary object
with its traceback. If cleanup fails, `InteractiveLifecycleError` retains the
primary object plus every named cleanup failure and uses the primary as its
explicit cause.

Daemon-backed and one-shot client adapters establish one
`source="client"` scope for the whole operation. Interactive retry markers and
their send attempts execute inside the same thread/turn scope; individual
audit writes inherit correlation instead of reconstructing it.

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
- Transcript content is intentionally preserved rather than diagnostically
  redacted. Internal transcript files use the shared private atomic-write
  boundary (`0700` directory, `0600` file), so a failed save cannot publish a
  partial transcript.
- Filename: includes the connection start time and export command time, e.g. `chat-default-20260514T120000123456Z-20260514T121500654321Z.md`.
- Output: after saving, print the file path and clipboard copy result. If `noclip` is used, do not attempt clipboard copying.

## Command Model

v0.2.0 reorganizes the command tree around user-facing concepts. This is a breaking cleanup; old command paths are removed instead of kept as compatibility aliases.

Top-level commands:

| Command         | Purpose                                                   |
| --------------- | --------------------------------------------------------- |
| `nuself`        | Open interactive chat by default                          |
| `nuself chat`   | Explicit chat entry                                       |
| `nuself attach` | Attach to a running daemon                                |
| `nuself daemon` | Background process lifecycle                              |
| `nuself thread` | Conversation thread management                            |
| `nuself memory` | Memory, sources, profile, review queue, graph             |
| `nuself inbox`  | User-facing proactive items: reflection and notifications |
| `nuself reason` | Long-run reasoning threads                                |
| `nuself trace`  | Thought provenance records                                |
| `nuself dev`    | Diagnostics, logs, config, health, eval, status           |

Breaking moves:

| Removed path                  | New path                                      |
| ----------------------------- | --------------------------------------------- |
| `nuself source ...`           | `nuself memory source ...`                    |
| `nuself reflection ...`       | `nuself inbox reflection ...`                 |
| `nuself notify ...`           | `nuself inbox notify ...`                     |
| `nuself logs ...`             | `nuself dev logs ...`                         |
| `nuself status`               | `nuself dev status` or `nuself daemon status` |
| `nuself health`               | `nuself dev health`                           |
| `nuself config`               | `nuself dev config`                           |
| `nuself eval`                 | `nuself dev eval`                             |
| `nuself memory candidate ...` | `nuself memory review ...`                    |
| `nuself thread create ...`    | `nuself thread new ...`                       |

Top-level help should group commands as:

- Daily: default chat, `chat`, `attach`
- Objects: `thread`, `memory`, `inbox`, `reason`, `trace`
- System: `daemon`, `dev`

Top-level help and command group help must show one-line descriptions for each listed command. Multi-layer groups must
do the same at every level, including `memory review`, `memory source`, `memory profile`, `memory graph`,
`inbox reflection`, and `inbox notify`, so users can choose commands without already knowing the subsystem vocabulary.

REPL commands mirror the same model:

| Command                 | Purpose                      |
| ----------------------- | ---------------------------- |
| `:inbox`, `:i`          | List pending proactive items |
| `:inbox reflection ...` | Reflection commands          |
| `:inbox notify ...`     | Notification commands        |
| `:mem`, `:m`            | Memory preview               |
| `:thread`, `:t`         | Thread switching/listing     |
| `:reason`               | Long-run reasoning commands  |
| `:trace`                | Thought provenance commands  |
| `:dev status`           | Session/system status        |
| `:restart`, `:r`        | Restart daemon and reconnect |
| `:export`, `:e`         | Transcript export            |

## Command Group Reference

### Reflection

```
nuself inbox reflection list [--status pending|dismissed|archived] [--json]
```

- **Default view**: All reflection entries.
- **`--status`**: Filter to one entry status.
- **Output**: Indexed record blocks. First line contains metadata only, e.g. `[<N>] [reflection] status=[<status>] created=<timestamp> type=<candidate_type> score=<composite>`; second line contains the reflection title as indented body text. The component tag and status tag are colored when color is enabled.
- **ID display**: Plain-text list output does not print long `reflection-candidate-*` entry IDs. Use the visible index directly, or use `--json` when the full ID is needed.
- **Empty**: `No reflection entries.`

```
nuself inbox reflection show <id_or_index> [--json]
```

- Indexes into the same filtered list used by `reflection list`.
- **Detail view**: One record header containing ID, status, candidate metadata, deep link, and timestamps; body text starts on the next indented line; discussion trace uses the indented discussion trace block.

```
nuself inbox reflection promote <id_or_index>
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
nuself daemon start | stop | restart | status | health | list
```

- **Output**: Plain text state lines
  (`daemon <stopped|owned_unready|ready|inconsistent> pid=... socket=...`).
- Restart success is one line:
  `Restarted: daemon <phase> pid=... socket=... stop=<outcome> start=<outcome>`.
  Interactive restart uses the same outcome fields.
- `daemon health` queries the running process and prints one line per background
  worker with `alive`, consecutive failures, last success, and last error.
- **Error**: State mismatch or typed startup failure printed to stderr with exit
  code `1`. Startup failures distinguish spawn failure, early child exit, and
  readiness timeout without printing the raw daemon process log.
- Stop and restart failures distinguish shutdown rejection, ownership
  inspection failure, and ownership-release timeout. They never signal a PID
  obtained only from a runtime metadata file.
- Status ownership-inspection failure prints a concise status-unavailable error
  and exits non-zero; it is never rendered as `stopped`.
- Every CLI surface uses the shared daemon-status observation boundary for this
  error rendering, including REPL `:dev status`. One command decision performs
  one initial observation; the default launcher passes that snapshot into
  startup rather than immediately repeating the same ping and lock probe.

### Memory

All memory subcommands follow the same list/detail/empty/error contracts.

- **Help**: `nuself memory -h` and nested group help (`memory review -h`, `memory source -h`, `memory profile -h`,
  `memory graph -h`) list every subcommand with a one-line purpose, following the shared command help contract.
- **List**: `[memory] [<N>] state=<state> type=<type> id=<id> tags=[...] confidence=...`, followed by indented title/body text. `<N>` is a 0-based visible index.
- **Preview**: `memory preview` and REPL `:mem` show memory entries with the same record-block style as `memory list`, but without visible indexes. It is for reading context, not as the authoritative handle source for object operations.
- **Detail**: Same record-block style as list, with full title/body plus tags, temporal metadata, and evidence rendered as indented body sections.
- `memory show/edit/delete`, `memory review show/accept/reject/edit/merge`, `memory source show/delete/chunks/extract`, and `memory profile show/delete` accept either a stable ID or the 0-based index from their corresponding list command.
- `memory delete`, `memory review accept`, and `memory review reject` also accept compact batch selections, such as `nuself memory delete 0-43` or `nuself memory review accept 1,3-5,9`.

## Discussion Trace Contract

Discussion traces rendered by `render_discussion_trace()` must:

1. Group entries by turn (`candidate`, `host`, `turn-N`).
2. Prefix each speaker utterance with `[speaker]` aligned to 18 columns.
3. Separate turns with a blank line.
4. Render the trace section title as a square-bracket tag, such as `[discussion]`.
5. Render each group header as a square-bracket tag, such as `[host]`, `[candidate]`, or `[turn-1]`.
6. If the group header and speaker are the same, render one tag followed by the content instead of repeating `[host] [host]` or `[candidate] [candidate]`.

## Approval And Event Boundaries

User confirmation is a synchronous request boundary, not a post-turn log
consumer. Approval-gated agent tools prompt through the interactive tool
wrapper before executing a durable or destructive action. A declined request
does not execute the action.

`proposal_created` and similar structured log entries are append-only audit
records. The CLI may render them as activity, but it must never replay a log
record to execute a proposal, deduplicate command execution, or reconstruct an
approval request. There is no `_PROPOSAL_HANDLERS` log-dispatch registry.

Ephemeral in-process activity may use `EventPublisher`. Cross-process commands
must use the daemon request protocol or a durable typed job contract. One-shot
mode cannot perform an interactive approval unless its invoked tool wrapper has
an input channel capable of obtaining that approval.
