# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close daemon socket transport audit ownership so read, dispatch, encode, and
delivery failures use one exact validated contract.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory socket read, request dispatch, response encoding, and response
   delivery failure producers, correlation, fallback state, and consumers.
2. Separate protocol rejections that produce ordinary failed responses from
   operational transport failures that require audit records.
3. Update error, runtime-infrastructure, log, and development specs before
   implementation.
4. Define one sealed daemon-transport audit registry with fixed messages and
   exact per-event metadata.
5. Route socket failure paths through the shared adapter without changing
   response fallback or connection-thread semantics.
6. Remove `_report_response_failure`, raw transport audit calls, free-form
   messages/defaults, and compatibility aliases.
7. Run focused and full quality gates, commit by functional boundary, and
   push.

## Out Of Scope

- No change to daemon request/response wire payloads.
- No retry of reads, dispatch, encoding, or delivery.
- No audit for clean peer disconnect or ordinary protocol rejection.
- No change to thread-per-connection ownership.

## Completion Evidence

- Daemon request audit ownership completed in `67d8cfe`.
- `request_rejected`, `chat_turn_failed`, `chat_turn_completed`, and
  `shutdown_requested` now use one sealed request-owned registry.
- Request handlers no longer choose audit messages, levels, statuses,
  error/duration policy, or metadata shape.
- Accepted shutdown has explicit `status="accepted"`.
- Initial next-batch inspection finds raw socket-server events for
  `request_transport_failed`, `request_failed`, `response_encode_failed`, and
  `response_delivery_failed`.
- Focused tests: 66 passed.
- Full suite: 2025 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Daemon request audit ownership was implemented in `67d8cfe`; milestone
publication is pending this goal update and push.

## Next Review Batch

Continue shared handler/log/message infrastructure review after daemon socket
transport audit ownership is verified and published.
