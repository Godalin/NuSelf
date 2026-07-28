# Notification Spec

## Purpose

The notification outbox is a durable user-attention and delivery queue for
"something happened, go look at X" notifications. It is not a generic internal
event bus and is **not** owned by reflection. Runtime control flow must not
publish arbitrary events to the outbox or consume notifications as commands.

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

- File storage uses one JSON file per entry under
  `private/notifications/outbox/{id}.json`; other configured storage backends
  preserve the same record contract.
- Writes use the shared atomic storage boundary.
- `get()` raises `OutboxEntryNotFound` if file missing.
- `created_at` and present `sent_at` values are non-empty, timezone-aware
  ISO-8601 strings. Naive timestamps are invalid because retention decisions
  must not depend on the host timezone.
- Each new entry stores the strict `RuntimeContext` active when the notification
  intent is created. State transitions preserve that context unchanged. This
  is domain-owned correlation on the durable outbox record, not a second
  `RuntimeEnvelope` around the entry.
- Records written before the context field existed decode with an empty
  `RuntimeContext`; the next state transition writes the current schema.
  Present context records remain strict and never guess malformed fields.
- `list()` isolates records with malformed fields through one payload-safe
  `outbox/record_decode_failed` diagnostic. It does not repair or delete them.
  `get()` is strict and propagates schema failures for the requested record.

### Dismissed Retention

`clear_dismissed_older_than(days)` removes dismissed entries whose `created_at`
instant is strictly earlier than the shared UTC clock minus `days * 24` hours.
`days` must be a non-negative integer and must not be a boolean. Entries exactly
at the cutoff are retained.

Record schema failures are isolated by `list()` before retention is evaluated.
Deletion is an authoritative storage mutation: delete failures propagate and
stop the cleanup instead of being reported as a malformed timestamp or silently
skipped. The delivery loop invokes this cleanup with seven days after processing
pending entries.

## Delivery Pipeline

### `NotificationDeliveryLoop.run_once()`

1. Lists only entries with `status="pending"`.
2. For each pending entry, exactly installs its saved correlation context and
   replaces `source` with `daemon.worker.notification_delivery` for the
   complete adapter/state-transition operation.
3. Iterates adapters in order.
4. **"All adapters must succeed" semantics**:
   - Each adapter's `send(entry)` must return `True`.
   - If any adapter returns `False`, the loop sets `success = False` and **breaks immediately** (subsequent adapters are not tried).
5. If `success` → `mark_sent()`.
6. If `!success` → `mark_failed()`.

The prior ambient context is restored after each entry even when an adapter
raises. Delivery logs therefore project the notification's originating
request/thread/turn/trace fields plus the delivery-owned source.

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
| `EmailNotificationAdapter` | `private/email.toml` with `[smtp]` and `[notification]` sections | `dry_run=True` logs intent | Missing config → `False` + `email_no_config`; invalid config → `email_config_invalid`, then delivery returns `False` + `email_no_config`; SMTP error → `False` + `email_failed` |

### Email Configuration

An absent `private/email.toml` is the normal disabled state and emits no
configuration diagnostic. When the file exists, decoding is strict:

- `[smtp]` and `[notification]` must be TOML tables;
- `smtp.host`, `notification.from`, and `notification.to` are required
  non-empty strings;
- `smtp.port` is an integer from 1 through 65535, excluding booleans;
- optional `smtp.use_tls` is a boolean;
- optional non-empty `smtp.user` and `smtp.password` must be present together.

Read failures, malformed TOML, and schema failures emit one payload-safe
`outbox/email_config_invalid` warning without raw values or credentials, then
leave the adapter disabled. Undeclared implementation failures propagate.
| `MacOSNotificationAdapter` | `osascript` on `$PATH` | `dry_run=True` logs intent | Missing `osascript` → returns `True` (graceful degradation); subprocess non-zero → `False` + `macos_failed` |

For real delivery failures, the adapter's `False` result is authoritative and
the associated `email_no_config`, `email_failed`, or `macos_failed` record is
an auxiliary diagnostic. Diagnostic and structured-log failure cannot replace
`False`; the delivery loop must still persist `failed` and increment attempts.

Log-only delivery, explicit dry runs, and the macOS-unavailable logging
fallback are different: their log write is the delivery effect itself, so its
failure remains authoritative and propagates.

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
