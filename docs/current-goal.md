# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Daemon response encoding is separate from byte delivery; an invalid or
oversized decided response produces an observed, request-correlated protocol
failure frame when the connection remains writable.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Invalid status/error combinations and oversized handler payloads emit
  `daemon/response_encode_failed` with request correlation and the decided
  response status.
- An unencodable response is replaced before the first write by one bounded
  error frame with the same request id.
- Structured diagnostic storage failure emits a runtime warning but does not
  prevent fallback-frame encoding or delivery.
- Fallback broken-pipe failure remains separately observable as
  `daemon/response_delivery_failed`, including frame status and
  `fallback=true`; no second frame is attempted after writing begins.
- Focused daemon transport, protocol, and server tests: 82 passed.
- Final full tests: 1344 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
daemon response encoding and byte delivery have distinct failure boundaries.
