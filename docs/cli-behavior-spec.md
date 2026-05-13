# NuSelf CLI & Interaction Behavior Spec

This document defines the user-visible behavior contract for NuSelf commands, REPL interactions, and event rendering. Changes to CLI output format, error handling, color conventions, or command semantics must update this spec.

---

## 1. Design Principles

1. **Consistency**: The same concept (e.g., a memory entry, an outbox item) must look similar across `list`, `show`, REPL, and logs.
2. **Lists are summaries, shows are details**: `list` prints one compact line per item. `show` prints a labeled multi-line block.
3. **Empty state is success**: "No items." goes to stdout with exit code `0`. Not-found goes to stderr with exit code `1`.
4. **Errors to stderr, success to stdout**: Never mix the two streams for the same semantic category.
5. **Color is informative, not required**: All colored output must degrade gracefully via `--no-color` or `NO_COLOR`.
6. **JSON mode is a first-class view**: Any command that prints structured data should support `--json` where practical.
7. **Separate user outcomes from internal audit**: `list` shows user-meaningful outcomes. `logs` shows the full internal audit trail.

---

## 2. Terminal Output Conventions

### 2.1 Color System

Color is controlled by `TerminalTheme` in `src/nuself/tui/render.py`.

- **Default ON** when `sys.stdout.isatty()` and `NO_COLOR` is not set.
- **Force OFF** with `--no-color` or `NO_COLOR=1`.

**Component tag colors:**

| Component | ANSI | Display Name |
|---|---|---|
| `daemon` | `90` (gray) | `daemon` |
| `chat` | `34` (blue) | `chat` |
| `memory` | `32` (green) | `memory` |
| `persona` | `35` (magenta) | `selves` |
| `outbox` | `36` (cyan) | `outbox` |
| `reflection` | `33` (yellow) | `reflection` |

**Semantic status colors:**

| State | Color | Used For |
|---|---|---|
| `approved`, `sent`, `accepted`, `reviewed` | green (`32`) | Positive terminal states |
| `rejected`, `failed`, `error` | red (`31`) | Negative terminal states |
| `pending`, `started`, `draft` | yellow (`33`) | In-progress or waiting states |
| `dismissed`, `skipped` | gray (`90`) | Inactive / no-op states |

### 2.2 List View Contract

- One line per item.
- Left-to-right: primary identifier → colored status tag → human title → muted metadata.
- Items are indexed only when the command accepts a numeric index for `show` (e.g., `reflection list` → `reflection show <idx>`).

### 2.3 Detail View Contract

- Labeled fields aligned on the first colon: `label: value`.
- Status fields use colored text.
- Body or long text appears after a blank line.
- Related sub-structures (scores, traces) are grouped under section headers with a blank line before the header.

### 2.4 Empty State Contract

| Context | Output | Stream | Exit Code |
|---|---|---|---|
| `list` with no items | `No <items>.` | stdout | `0` |
| `show` with invalid ID | `<Item> not found: <id>` | stderr | `1` |
| `search` with no matches | `No matching <items>.` | stdout | `0` |
| `delete` with invalid ID | `<Item> not found: <id>` | stderr | `1` |

### 2.5 JSON Mode Contract

- Flag name: `--json` (or `--as-json` where parser conflicts require it).
- Prints one JSON object per line (JSONL) for lists.
- Prints one JSON object for single-item `show`.
- Disables color automatically.
- Uses `sort_keys=True, ensure_ascii=True`.

---

## 3. REPL Conventions

### 3.1 Command Prefix

All interactive commands start with `:`.

### 3.2 Output Formatting

- Commands wrap their output with leading and trailing blank lines for visual separation.
- After every non-command user turn, the session header is reprinted:
  ```
  session thread=<id> daemon=<running|one-shot>
  ```
- After thread-switching commands (`:thread`, `:rename`, `:branch`, `:archive`, `:delete`), the header is also reprinted.

### 3.3 Activity Printing

After each chat turn, the REPL prints **all new log events** that occurred during that turn using `render_log_event()`. This provides both immediate feedback and an audit trail.

---

## 4. Event Taxonomy & Visibility

### 4.1 Log Components

Six components write to `private/logs/`:

| Component | Log File | Purpose |
|---|---|---|
| `daemon` | `daemon.log` | Daemon lifecycle |
| `chat` | `chat.log` | Conversation turns |
| `memory` | `memory.log` | Memory curation/optimization |
| `persona` | `persona.log` | Persona activations, host decisions |
| `outbox` | `outbox.log` | Notification delivery attempts |
| `reflection` | `reflection.log` | Reflection scheduler events |

### 4.2 Reflection Events

The reflection scheduler emits these events into `reflection.log`:

| Event | Status | Audience | Visibility |
|---|---|---|---|
| `cycle_started` | `started` | Internal audit | `logs --component reflection` only |
| `candidate_generation_skipped` | `skipped` | Internal audit | `logs --component reflection` only |
| `candidate_generation_failed` | `error` | Internal audit | `logs --component reflection` only |
| `cycle_no_candidates` | `completed` | Internal audit | `logs --component reflection` only |
| `cycle_filtered` | `completed` | Internal audit | `logs --component reflection` only |
| `persona_discussion` | `approved` / `rejected` | User outcome | **`reflection list`** AND logs |
| `cycle_discussion_rejected` | `completed` | Internal audit | `logs --component reflection` only |
| `cycle_completed` | `completed` | Internal audit | `logs --component reflection` only |

**`reflection list` must display only `persona_discussion` events by default.**
All other reflection events are scheduler internals and belong in `nuself logs --component reflection`.

### 4.3 Notification States

| State | Color | Meaning |
|---|---|---|
| `pending` | yellow | Waiting for delivery |
| `sent` | green | Successfully delivered |
| `failed` | red | Delivery failed |
| `dismissed` | gray | User dismissed |

---

## 5. Command Group Reference

### 5.1 Reflection

```
nuself reflection list [--tail N] [--include-all] [--json]
```

- **Default view**: Only `persona_discussion` events (approved/rejected outcomes).
- **`--include-all`**: Show all reflection events (including scheduler internals).
- **Output**: Indexed compact lines `[  N] <time> [<status>] <message>  score=<composite>`.
- **Empty**: `No reflection events.`

```
nuself reflection show <event_index> [--tail N] [--include-all] [--json]
```

- Indexes into the same filtered list used by `reflection list`.
- **Detail view**: Time, status, message, candidate metadata, persona score bars, blocking vetos, winners, emergent personas, revised title/body, and grouped discussion trace.

### 5.2 Logs

```
nuself logs [--component <c>] [--tail N] [--json] [--no-color]
```

- **Purpose**: Raw audit trail. No filtering by event semantics.
- **Output**: `[component_tag] message status=... duration=...ms thread=... request=... error=...`

### 5.3 Notifications

```
nuself notify list [--status <state>]
```

- **Output**: `<id> [<status>] title created=... attempts=... link|-`
- `--status` filters at the outbox level.

```
nuself notify show <id>
```

- **Output**: Labeled multi-line block with body.

### 5.4 Memory

All memory subcommands follow the same list/detail/empty/error contracts.

```
nuself memory list [--sort-by <field>] [--review-state <state>]
nuself memory show <id>
nuself memory search <query> [...filters]
```

- **List**: `[mem] <state_color>reviewed</> <type> <id> Title #tags conf=...`
- **Detail**: Header + metadata + tags + evidence + wrapped body.

### 5.5 Daemon

```
nuself daemon start | stop | restart | status | list
```

- **Output**: Plain text state lines (`daemon running pid=... socket=...`).
- **Error**: State mismatch printed to stderr with exit code `1`.

---

## 6. Rendering Layer Contracts

All terminal rendering lives in `src/nuself/tui/` and is divided into:

- **`render.py`**: Compact renderers for logs, outbox, reflection, host decisions, discussion traces.
- **`memory.py`**: Rich renderers for memory entries, candidates, profile items, sources, relations.

### 6.1 Adding a New Renderer

1. Accept `color: bool | None = None` and delegate to `TerminalTheme`.
2. Return `str` for single-line, `list[str]` for multi-line.
3. Use muted color (`90`) for IDs, timestamps, and secondary metadata.
4. Use semantic status colors for state labels.
5. Handle `None`/missing fields gracefully.

### 6.2 Discussion Trace Contract

Discussion traces rendered by `render_discussion_trace()` must:

1. Group entries by turn (`candidate`, `host`, `turn-N`).
2. Prefix each speaker utterance with `[speaker]` aligned to 18 columns.
3. Separate turns with a blank line.
4. Use `── turn-label ──` as turn headers.

---

## 7. Change Policy

- This spec is authoritative. When a command's output format, filtering logic, or error behavior changes, this document must be updated in the same commit.
- When a new command is added, it must include a section here before the feature commit lands.
- README examples must stay synchronized with this spec, but this spec is the source of truth for behavioral contracts.
