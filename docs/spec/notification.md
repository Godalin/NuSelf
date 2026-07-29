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

The global status is a compatibility projection over durable per-adapter
delivery state, not the sole delivery truth. Each entry may contain:

- `required_adapters`: the ordered, unique stable adapter IDs frozen on its
  first delivery attempt;
- `deliveries`: one state per required adapter with `pending`, `sent`, or
  `failed`, its own attempt count, and optional successful-delivery timestamp.

`sent` means every required adapter is `sent`; `failed` means at least one
required adapter is `failed` after an attempt completes; otherwise the entry
remains `pending`. `dismissed` remains an explicit user override. Records from
before adapter delivery state existed decode with an empty plan and acquire it
atomically on their first subsequent delivery attempt.

### Valid Transitions

```
add() ──► pending
pending ──► sent      [finalize_delivery] triggered by: DeliveryLoop, CLI notify send
pending ──► failed    [finalize_delivery] triggered by: DeliveryLoop, CLI notify send
any     ──► dismissed [dismiss]        triggered by: CLI notify dismiss
any     ──► deleted   [clear(status)]  triggered by: CLI notify clear
```

There is no legacy whole-entry `mark_sent` or `mark_failed` transition.
Delivery always freezes a required adapter plan, records each adapter result,
then derives the compatibility status. `dismiss()` changes only the global
status and preserves the complete adapter plan and history.

### Persistence

- File storage uses one JSON file per entry under
  `private/notifications/outbox/{id}.json`; other configured storage backends
  preserve the same record contract.
- Writes use the shared atomic storage boundary.
- `add()` performs idempotency-key lookup and insertion inside one backend
  transaction. Competing threads, backend instances, and processes using the
  same file or SQLite store therefore return one existing record rather than
  creating multiple records for one idempotency key.
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
3. Validates that configured adapters expose non-empty, unique stable
   `delivery_id` values, then atomically freezes those IDs as the entry's
   required plan if it has no plan yet. Duplicate or invalid IDs fail before
   any adapter side effect.
4. Iterates the frozen required adapter IDs in order. Every adapter with a
   durable terminal result (`sent` or `failed`) is skipped. Each available
   `pending` adapter is invoked once and its success or failure is persisted
   immediately before the next adapter runs.
   A required adapter missing from the current configuration is persisted as
   failed without inventing a replacement identity.
5. After every required adapter has a durable result, derives and persists the
   global status. A crash after a failed result but before finalization leaves
   the entry globally `pending`; the next run skips both successful and failed
   terminal adapter states and only finalizes the projection.

The CLI and REPL `notify send` path use this same pipeline with the stable
`log` adapter. They never directly overwrite global status. If an entry already
has another frozen adapter plan, the command preserves that plan, records any
still-pending unavailable adapters as failed, skips prior terminal results, and
finalizes the projection.

The prior ambient context is restored after each entry even when an adapter
raises. Delivery logs therefore project the notification's originating
request/thread/turn/trace fields plus the delivery-owned source.

### Retry Behavior

**No automatic retry after a completed failed attempt.** A globally failed
entry stays `failed` forever. Crash recovery of an incomplete pending attempt
is not a retry of adapters already recorded as sent or failed. A future retry
feature must explicitly reset selected failed adapter states to `pending`;
normal delivery and finalization cannot do so.

### Daemon Integration

- Background thread: `nuself-notification-delivery`.
- Poll interval: `config.daemon.notification_delivery.interval_seconds` (default `30`).
- Tick errors caught and swallowed (`except RuntimeError: continue`).

## Adapters

| Adapter | Preconditions | Dry Run | Failure Mode |
|---|---|---|---|
| `LogOnlyNotificationAdapter` | None | N/A | Always returns `True`; writes to `outbox.log` |
| `EmailNotificationAdapter` | `private/email.toml` with `[smtp]` and `[notification]` sections | `dry_run=True` logs intent | Missing config → `False` + `email_no_config`; invalid config → `email_config_invalid`, then delivery returns `False` + `email_no_config`; SMTP error → `False` + `email_failed` |
| `MacOSNotificationAdapter` | `osascript` on `$PATH` | `dry_run=True` logs intent | Missing `osascript` → returns `True` (graceful degradation); subprocess non-zero → `False` + `macos_failed` |

Built-in stable delivery IDs are `log`, `email`, and `macos`. Third-party
adapters must supply their own non-empty stable ID; class names and error text
must never be used as persisted identities.

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

For real delivery failures, the adapter's `False` result is authoritative and
the associated `email_no_config`, `email_failed`, or `macos_failed` record is
an auxiliary diagnostic. Diagnostic and structured-log failure cannot replace
`False`; the delivery loop must still persist `failed` and increment attempts.

Log-only delivery, explicit dry runs, and the macOS-unavailable logging
fallback are different: their log write is the delivery effect itself, so its
failure remains authoritative and propagates.

Real email delivery constructs the complete `EmailMessage` inside the declared
adapter failure boundary. Declared `ValueError` from invalid subject/from/to
headers, MIME construction, or deep-link validation returns `False` and emits
`email_failed` just like an SMTP failure; it does not escape raw. Unexpected
implementation `TypeError` remains outside the recovery boundary.

The plain-text part contains the original body. The HTML alternative escapes
the body as text and escapes the link separately as an HTML attribute. An HTML
alternative is created only after `DeepLink.parse()` accepts the URL as a
supported `nuself` action; the adapter uses the parsed link's canonical
`to_url()` result and rejects HTTP(S), unknown paths, fragments, or malformed
links. Email configuration rejects control characters in sender and recipient
headers before an adapter is enabled.

### Delivery Audit Contract

Notification owns every direct `component=outbox` delivery audit. Adapters use
Notification-domain projection functions and do not choose raw event names,
levels, statuses, or metadata shapes.

| Event | Level | Status | Metadata |
|---|---|---|---|
| `outbox_delivered` | `info` | `delivered` | non-empty `entry_id`, non-negative `attempt` |
| `email_dry_run` | `debug` | `simulated` | non-empty `entry_id`, non-negative `attempt` |
| `email_no_config` | `warning` | `failed` | required error, non-empty `entry_id`, non-negative `attempt` |
| `email_failed` | `warning` | `failed` | required error, non-empty `entry_id`, non-negative `attempt` |
| `email_config_invalid` | `warning` | `degraded` | required error, fixed config record name |
| `macos_dry_run` | `debug` | `simulated` | non-empty `entry_id`, non-negative `attempt` |
| `macos_unavailable` | `info` | `unavailable` | non-empty `entry_id`, non-negative `attempt` |
| `macos_failed` | `warning` | `failed` | required error, non-empty `entry_id`, non-negative `attempt` |

The outbox entry is the authoritative private notification record. Delivery
audits must not duplicate its title, body, deep link, idempotency key, runtime
context, recipient, or SMTP configuration. Messages are fixed operational
descriptions. The sanitized structured error is the only failure detail.
Unknown identities or schema violations fail before the sink; generic
corrupt-record diagnostics remain owned by shared observability.

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
