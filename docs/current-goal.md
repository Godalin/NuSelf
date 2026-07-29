# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close daemon request audit ownership so request rejection, chat completion and
failure, and shutdown intent use one exact validated contract.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory every daemon request audit producer, message, status/error policy,
   duration, metadata, correlation, and renderer/test consumer.
2. Separate request decision records from transport and Chat-domain audits;
   remove semantic duplication where an owner already records the event.
3. Update error, daemon protocol, log, and development specs before
   implementation.
4. Define one sealed daemon-request audit registry with fixed messages and
   exact per-event metadata.
5. Route rejection, chat result, and shutdown boundaries through the shared
   adapter without changing response or shutdown decisions.
6. Remove `_write_request_audit_event`, raw request log calls, free-form
   defaults, and compatibility aliases.
7. Run focused and full quality gates, commit by functional boundary, and
   push.

## Out Of Scope

- No change to daemon request/response wire payloads.
- No change to request handler dispatch or middleware ordering.
- No change to ConversationGraphRuntime ownership.
- No change to socket transport delivery diagnostics.

## Completion Evidence

- Observability failure ownership completed in `427cf31`.
- All secondary log writes now use
  `observability_projection_failed` with exact `failed_event` metadata.
- All observed EventPublisher subscriber failures now use
  `internal_event_delivery_failed` with exact envelope event/producer
  metadata.
- Thirteen subsystem-specific write/delivery aliases and all caller-selected
  failure projection parameters were removed.
- Auxiliary log schema validation now runs before the best-effort sink
  boundary.
- Initial next-batch inspection finds raw daemon request events for
  `request_rejected`, `chat_turn_failed`, `chat_turn_completed`, and
  `shutdown_requested`.
- Focused migration tests: 251 passed; observability boundary tests: 26 passed.
- Full suite: 2021 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Observability failure ownership was implemented in `427cf31`; milestone
publication is pending this goal update and push.

## Next Review Batch

Continue shared handler/log/message infrastructure review after daemon request
audit ownership is verified and published.
