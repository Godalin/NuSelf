# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Give Notification delivery one closed, privacy-minimal audit contract owned by
the Notification subsystem.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory log-only, email, macOS, config-decode, and delivery-loop audit
   producers.
2. Define one Notification-owned event taxonomy and privacy boundary.
3. Register exact level/status/error/metadata contracts for all owned events.
4. Route adapters and configuration failures through Notification-owned
   projection adapters.
5. Separate authoritative outbox content from delivery audit records.
6. Verify titles, bodies, deep links, idempotency keys, recipients, and SMTP
   configuration never enter Notification audit records.
7. Run full quality gates, commit, and push.

## Out Of Scope

- No process-global registry containing every domain's audit events.
- No migration or rewriting of historical JSONL records.
- No change to outbox state transitions, retry count, adapter ordering, or
  delivery success semantics.
- No removal of notification content from authoritative outbox entries or
  external email/macOS delivery payloads; only audit projection is minimized.
- Generic corrupt-record diagnostics remain owned by observability.
- Generic audit-projection failure events remain owned by observability.

## Completion Evidence

- The inventory covers log-only delivery, email/macOS dry runs, unavailable
  platform delivery, missing/invalid email configuration, SMTP failure, and
  macOS subprocess failure.
- One sealed `notification.audit` registry owns all eight direct delivery
  event identities and their exact level, status, error, and metadata
  contracts.
- Log-only, email, and macOS adapters now use Notification-owned adapters
  instead of constructing raw `outbox` log records.
- Delivery audits retain only an entry id plus zero-based attempt count, or the
  fixed `email.toml` record name for configuration decoding.
- Notification title/body, deep link, idempotency key, runtime context,
  recipient, and SMTP data remain in their authoritative/private delivery
  locations and are absent from audit messages and metadata.
- Log-only, explicit dry-run, and macOS-unavailable writes remain
  authoritative delivery effects: sink failure propagates instead of marking
  an undelivered entry sent.
- Caught adapter/configuration failures remain best-effort diagnostics and
  cannot replace the adapter's `False` result or the outbox failed transition.
- Generic malformed outbox-record diagnostics remain owned by shared
  observability and are not duplicated into the delivery registry.
- Direct tests cover all eight canonical schemas, unknown metadata, unknown
  identities, pre-sink rejection, projection privacy, and delivery-context
  preservation.
- Focused Notification/outbox suites: `77 passed`.
- Full test suite: `1919 passed`.
- Pyright 1.1.409: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is ready to publish through implementation commit `e270dc2`.

## Next Review Batch

Review Chat/REPL audit schema ownership.
