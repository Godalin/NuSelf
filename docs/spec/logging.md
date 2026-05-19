# Logging Spec

## LogEvent Structure

| Field | Type | Required |
|---|---|---|
| `time` | `str` (ISO) | yes |
| `level` | `"debug" \| "info" \| "warning" \| "error"` | yes |
| `component` | `LogComponent` | yes |
| `event` | `str` (slug) | yes |
| `message` | `str` | yes |
| `thread_id` | `str \| None` | no |
| `request_id` | `str \| None` | no |
| `node` | `str \| None` | no |
| `duration_ms` | `int \| None` | no |
| `status` | `str \| None` | no |
| `error` | `str \| None` | no |
| `metadata` | `dict[str, object] \| None` | no |

Serialization (`to_record()`) omits `None`-valued optional fields.

## Log Components

| Component | File | Responsibility |
|---|---|---|
| `daemon` | `daemon.log` | Daemon lifecycle |
| `chat` | `chat.log` | Conversation turns |
| `memory` | `memory.log` | Memory operations |
| `persona` | `persona.log` | Persona activations, host decisions, competitive persona discussions |
| `outbox` | `outbox.log` | Notification delivery attempts |
| `reflection` | `reflection.log` | Reflection scheduling |

Display name mapping: `persona` → `selves`.

## Write Contract

- JSON Lines format (`sort_keys=True`, `ensure_ascii=True`).
- Append mode (`"a"`, `encoding="utf-8"`).
- Directory creation before open.
- Returns the constructed `LogEvent`.

## Read Contract

- `component=None` reads all 6 files; otherwise reads exactly one.
- Missing file → silently skip.
- All events sorted ascending by `time` (global chronological order).
- `tail > 0` returns `events[-tail:]`.
- Non-JSON lines wrapped as `event="legacy"`.
- Invalid JSON lines skipped.

## Log Rotation

**No rotation or truncation policy exists.** Logs grow indefinitely.
