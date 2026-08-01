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
| `failed` | At least one adapter failed or has uncertain delivery |
| `dismissed` | User explicitly dismissed |

The global status is a compatibility projection over durable per-adapter
delivery state, not the sole delivery truth. Each entry may contain:

- `required_adapters`: the ordered, unique stable adapter IDs frozen on its
  first delivery attempt;
- `deliveries`: one state per required adapter with `pending`, `delivering`,
  `sent`, `failed`, or `uncertain`, its own attempt count, and optional
  successful-delivery timestamp.

`sent` means every required adapter is `sent`; `failed` means at least one
required adapter is `failed` or `uncertain` after an attempt completes;
otherwise the entry remains `pending`. `dismissed` remains an explicit user
override. Records from
before adapter delivery state existed decode with an empty plan and acquire it
atomically on their first subsequent delivery attempt.

### Valid Transitions

```
add() ──► pending
pending ──► sent      [finalize_delivery] triggered by: DeliveryLoop, CLI notify send
pending ──► failed    [finalize_delivery] triggered by: DeliveryLoop, CLI notify send
any     ──► dismissed [dismiss]        triggered by: CLI notify dismiss
terminal ─► deleted   [clear(selection)] triggered by: CLI notify clear
```

There is no legacy whole-entry `mark_sent` or `mark_failed` transition.
Delivery always freezes a required adapter plan, records each attempt before
its external effect and each known result afterward, then derives the
compatibility status. `dismiss()` changes only the global status and preserves
the complete adapter plan and history.

### Persistence

- File storage uses one JSON file per entry under
  `<authority-root>/notifications/outbox/{id}.json`; other configured storage backends
  preserve the same record contract.
- Writes use the shared atomic storage boundary.
- `add()` performs idempotency-key lookup and insertion inside one backend
  transaction. Competing threads, backend instances, and processes using the
  same file or SQLite store therefore return one existing record rather than
  creating multiple records for one idempotency key.
- `get()` raises `OutboxEntryNotFound` if file missing.
- Every delivery, dismiss, and deletion operation for one entry holds the same
  stable cross-process lock under `<authority-root>/notifications/locks/` from its
  authoritative read through its final persistence mutation. Two processes
  cannot send the same adapter concurrently, and dismiss/clear cannot race a
  completed external effect or be overwritten by delivery finalization.
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

Loop composition validates and indexes its ordered adapter plan once. Invalid
or duplicate stable IDs therefore fail before polling begins; later caller
mutation of the source list cannot alter the live loop. Standalone
single-entry delivery validates its supplied plan at that call boundary.

1. Lists only entries with `status="pending"`.
2. For each pending entry, exactly installs its saved correlation context and
   replaces `source` with `daemon.worker.notification_delivery` for the
   complete adapter/state-transition operation.
3. Atomically freezes the already-validated adapter IDs as the entry's required
   plan if it has no plan yet. Duplicate or invalid IDs fail before any adapter
   side effect.
4. Converts any recovered `delivering` state to `uncertain`; such an attempt is
   never automatically replayed because the external effect may already have
   occurred.
5. Iterates the frozen required adapter IDs in order. Every adapter with a
   durable terminal result (`sent`, `failed`, or `uncertain`) is skipped. Each
   available `pending` adapter is first persisted as `delivering` with its
   incremented attempt count, then invoked once, and its success or failure is
   persisted immediately before the next adapter runs.
   A required adapter missing from the current configuration is persisted as
   failed without inventing a replacement identity.
6. After every required adapter has a durable result, derives and persists the
   global status. A crash after a failed result but before finalization leaves
   the entry globally `pending`; the next run skips both successful and failed
   terminal adapter states and only finalizes the projection.

Daemon, CLI, and REPL build adapters through the same
`build_notification_adapters(project_root)` composition root, preserving the
same order and stable IDs. The builder returns an immutable tuple; adapter-plan
mutation is not a runtime extension mechanism. They never directly overwrite
global status. If an
entry already has another frozen adapter plan, the command preserves that
plan, records any still-pending unavailable adapters as failed, skips prior
terminal results, and finalizes the projection.

The prior ambient context is restored after each entry even when an adapter
raises. Delivery logs therefore project the notification's originating
request/thread/turn/trace fields plus the delivery-owned source.

### Retry Behavior

**No automatic retry after a completed or uncertain attempt.** A globally
failed entry stays `failed` forever. SMTP and other non-idempotent adapters are
therefore at-most-once after intent persistence: a crash after the external
send but before result persistence may leave delivery uncertain, but normal
recovery will not duplicate the effect. A future retry command must explicitly
reset selected failed or uncertain adapter states to `pending`; normal
delivery and finalization cannot do so.

### Daemon Integration

- Background thread: `nuself-notification-delivery`.
- Poll interval: `config.daemon.notification_delivery.interval_seconds` (default `30`).
- Tick errors caught and swallowed (`except RuntimeError: continue`).

## Adapters

| Adapter | Preconditions | Dry Run | Failure Mode |
|---|---|---|---|
| `LogOnlyNotificationAdapter` | None | N/A | Always returns `True`; writes to `outbox.log` |
| `EmailNotificationAdapter` | enabled unified `email` configuration | `dry_run=True` logs intent | Disabled config → `False` + `email_no_config`; SMTP error → `False` + `email_failed` |
| `MacOSNotificationAdapter` | `osascript` on `$PATH` | `dry_run=True` logs intent | Missing `osascript` → returns `True` (graceful degradation); subprocess non-zero → `False` + `macos_failed` |

Notification composition passes `MacOSNotificationAdapter` one already-resolved
project `Path`. The adapter does not accept an omitted authority or call
`runtime_paths()` internally.

The adapter snapshots `osascript` availability privately at construction.
Availability is not a mutable public control surface; tests control executable
discovery at the `shutil.which()` boundary before constructing the adapter.

Built-in stable delivery IDs are `log`, `email`, and `macos`. Third-party
adapters must supply their own non-empty stable ID; class names and error text
must never be used as persisted identities.

### Email Configuration

Email consumes the unified, already validated `SystemConfig.email` model.
There is no adapter-local parser or second credential file. The canonical
adapter builder includes email only when enabled.

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
| `nuself://conversation/<id>` | `open_conversation`, `conversation_id=<id>` |
| `nuself://conversation/<id>?message=...` | `open_conversation` + optional message |
| `nuself://new-conversation` | `new_conversation` |
| `nuself://new-conversation?title=...&message=...&candidate_id=...` | `new_conversation` with params |

Thread IDs are encoded as a single path segment. Query values use standard URL encoding, so messages, titles, and candidate IDs may contain `/`, `&`, `=`, spaces, or non-ASCII text and round-trip through `DeepLink.to_url()` / `DeepLink.parse()`.

## CLI / REPL Contracts

| Command | Exit Code | Output |
|---|---|---|
| `notify list [--status]` | `0` | Summary lines or `No outbox entries.` |
| `notify show <id>` | `0` if found, `1` if missing | Multi-line detail |
| `notify send <id>` | `0` on success, `1` on failure | Uses the canonical configured adapter plan |
| `notify dismiss <id>` | `0` if found, `1` if missing | `Dismissed: {id}` |
| `notify watch [--interval]` | `0` (Ctrl+C) | Polls every N seconds (default `5`, min `1`) |
| `notify clear [--status sent\|failed\|dismissed\|all-terminal]` | `0` | Removes the selected terminal entries; default is `all-terminal` |
| `notify stats` | `0` | Count table: Total, Pending, Sent, Failed, Dismissed |

Plain-text `notify list` and `notify show` output follows the shared CLI record renderer: one header line with `key=value` metadata, then body text on subsequent indented lines. `notify show` must not use a separate colon-aligned field table.

REPL `:notify` lists **only pending** entries. `:notify list` lists **all** entries.

Notification cleanup never deletes `pending` entries. Global `failed` includes
entries whose adapter plan ended in `failed` or `uncertain`, so
`--status failed` is the explicit cleanup path for both known failures and
crash-after-send ambiguity. `all-terminal` removes `sent`, `failed`, and
`dismissed` entries under the same per-entry serialization used by delivery
and dismissal.
