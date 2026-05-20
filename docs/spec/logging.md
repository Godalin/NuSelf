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

## Service Call Logs

When one subsystem invokes another subsystem through an agent-facing service/tool boundary, write a caller-owned log event with a service tag in metadata.

Example: chat calling a memory service tool writes a `chat` component event:

```json
{"component":"chat","event":"service_tool_called","metadata":{"service_component":"memory","tool":"memory_archive"}}
```

Human-readable rendering must show both tags at the front:

```text
[chat] [memory] service_tool_called status=completed tool=memory_archive
  args: {"entry_id": "m1"}
  result: Archived "Old memory".
```

Rules:

- The first tag is the caller component and determines the log file.
- The second tag is `metadata.service_component` and names the service being called.
- `service_component` is a display tag, not a normal `key=value` header field.
- Agent-facing chat tools for memory, reflection, reason, and trace all write `chat/service_tool_called` with the corresponding service tag.
- All other log formatting rules remain unchanged.
- Tool/service call body text is for debugging. It should include compact `args:` plus `result:` or `error:` lines, bounded in length so interactive output remains readable.

## Log Components

| Component | File | Responsibility |
|---|---|---|
| `daemon` | `daemon.log` | Daemon lifecycle |
| `chat` | `chat.log` | Conversation turns |
| `memory` | `memory.log` | Memory operations |
| `persona` | `persona.log` | Persona activations, host decisions, competitive persona discussions |
| `outbox` | `outbox.log` | Notification delivery attempts |
| `reflection` | `reflection.log` | Reflection scheduling |
| `reasoning` | `reasoning.log` | Long-run reasoning threads |

Display name mapping: `persona` → `selves`.

## Write Contract

- JSON Lines format (`sort_keys=True`, `ensure_ascii=True`).
- Append mode (`"a"`, `encoding="utf-8"`).
- Directory creation before open.
- Returns the constructed `LogEvent`.

## Read Contract

- `component=None` reads all component files; otherwise reads exactly one.
- Missing file → silently skip.
- All events sorted ascending by `time` (global chronological order).
- `tail > 0` returns `events[-tail:]`.
- Non-JSON lines wrapped as `event="legacy"`.
- Invalid JSON lines skipped.

## Log Rotation

**No rotation or truncation policy exists.** Logs grow indefinitely.
