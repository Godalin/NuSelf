# Notification Spec

## Purpose

The notification outbox is a **generic event bus** for "something happened, go look at X" style events. It is **not** owned by reflection.

Sources that may create outbox entries:
- Reflection scheduler (when `reflection.auto_notify` is `true`)
- Memory curator (future)
- Memory optimizer (future)
- Any background job that needs user attention

## Outbox State Machine

### States

| Status | Meaning |
|---|---|
| `pending` | Awaiting delivery |
| `sent` | Successfully delivered by all adapters |
| `failed` | At least one adapter failed |
| `dismissed` | User explicitly dismissed |

### Valid Transitions

```
add() ──► pending
pending ──► sent      [mark_sent]      triggered by: DeliveryLoop, CLI notify send
pending ──► failed    [mark_failed]    triggered by: DeliveryLoop, CLI notify send
any     ──► dismissed [dismiss]        triggered by: CLI notify dismiss
any     ──► deleted   [clear(status)]  triggered by: CLI notify clear
```

**No transition guards enforced in code.** Calling `mark_sent` on an already-sent entry is accepted and increments `attempts`.

### Persistence

- One JSON file per entry: `private/outbox/{id}.json`.
- Atomic write via `.tmp` + `replace()`.
- `get()` raises `OutboxEntryNotFound` if file missing.

## Delivery Pipeline

### `NotificationDeliveryLoop.run_once()`

1. Lists only entries with `status="pending"`.
2. For each pending entry, iterates adapters in order.
3. **"All adapters must succeed" semantics**:
   - Each adapter's `send(entry)` must return `True`.
   - If any adapter returns `False`, the loop sets `success = False` and **breaks immediately** (subsequent adapters are not tried).
4. If `success` → `mark_sent()`.
5. If `!success` → `mark_failed()`.

### Retry Behavior

**No automatic retry.** A failed entry stays `failed` forever. No backoff, no re-queueing.

### Daemon Integration

- Background thread: `nuself-notification-delivery`.
- Poll interval: `config.daemon.notification_delivery.interval_seconds` (default `30`).
- Tick errors caught and swallowed (`except RuntimeError: continue`).

## Adapters

| Adapter | Preconditions | Dry Run | Failure Mode |
|---|---|---|---|
| `LogOnlyNotificationAdapter` | None | N/A | Always returns `True`; writes to `outbox.log` |
| `EmailNotificationAdapter` | `private/email.toml` with `[smtp]` and `[notification]` sections | `dry_run=True` logs intent | Missing config → `False` + `email_no_config`; SMTP error → `False` + `email_failed` |
| `MacOSNotificationAdapter` | `osascript` on `$PATH` | `dry_run=True` logs intent | Missing `osascript` → returns `True` (graceful degradation); subprocess non-zero → `False` + `macos_failed` |

## Deep Links

### Supported URL Formats

| Format | Parses to |
|---|---|
| `nuself://thread/<id>` | `open_thread`, `thread_id=<id>` |
| `nuself://thread/<id>?message=...` | `open_thread` + optional message |
| `nuself://new-thread` | `new_thread` |
| `nuself://new-thread?title=...&message=...&candidate_id=...` | `new_thread` with params |

Thread IDs are encoded as a single path segment. Query values use standard URL encoding, so messages, titles, and candidate IDs may contain `/`, `&`, `=`, spaces, or non-ASCII text and round-trip through `DeepLink.to_url()` / `DeepLink.parse()`.

## CLI / REPL Contracts

| Command | Exit Code | Output |
|---|---|---|
| `notify list [--status]` | `0` | Summary lines or `No outbox entries.` |
| `notify show <id>` | `0` if found, `1` if missing | Multi-line detail |
| `notify send <id>` | `0` on success, `1` on failure | Uses **only** `LogOnlyNotificationAdapter` |
| `notify dismiss <id>` | `0` if found, `1` if missing | `Dismissed: {id}` |
| `notify watch [--interval]` | `0` (Ctrl+C) | Polls every N seconds (default `5`, min `1`) |
| `notify clear` | `0` | Removes all `dismissed` entries |
| `notify stats` | `0` | Count table: Total, Pending, Sent, Failed, Dismissed |

Plain-text `notify list` and `notify show` output follows the shared CLI record renderer: one header line with `key=value` metadata, then body text on subsequent indented lines. `notify show` must not use a separate colon-aligned field table.

REPL `:notify` lists **only pending** entries. `:notify list` lists **all** entries.
