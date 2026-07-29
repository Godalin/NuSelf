# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Separate daemon protocol errors by source. Request envelope decode, direct
request-payload decode, and registered handler invocation must not share an
exception classifier merely because they can all raise `ProtocolError`.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit event, log, job, and daemon projection/dispatch exception sources.
2. Verify structurally wrapped boundaries and identify type-only classifiers.
3. Reproduce raw `ProtocolError` from a registered daemon handler.
4. Specify envelope, payload, and invocation phase ownership.
5. Wrap direct payload codec failures with a typed source error and separate
   socket envelope decode from handler invocation.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No change to daemon wire format or payload schemas.
- No change to user-facing malformed-payload messages.
- No suppression of unexpected handler failures.
- No retry or transport policy change.

## Completion Evidence

- Event publication structurally wraps projection failures in a publisher-owned
  `EventDeliveryError`; a projection's same-typed exception remains nested.
- Log observers are caught at the direct invocation point and do not infer
  source from a domain exception type.
- Job admission performs no exception translation.
- Daemon `handle_request(...)` currently catches any `ProtocolError` from the
  complete registered handler invocation and labels it `request_rejected`.
- The socket adapter also catches `ProtocolError` around both
  `DaemonRequest.from_json_line(...)` and `handle_request(...)`, so a raw
  handler failure can masquerade as malformed request-envelope input.
- `DaemonRequestPayloadError` now marks only a direct request-specific payload
  codec rejection and retains the original `ProtocolError` as its cause.
- Every daemon request handler routes its direct payload decode through the
  shared typed wrapper; `echo` remains the deliberate arbitrary-object
  exception.
- `handle_request(...)` translates only `DaemonRequestPayloadError`. A raw
  `ProtocolError` raised later by a registered handler preserves its exact
  identity.
- Socket request-envelope decoding and handler invocation now have separate
  lexical catches. A handler `ProtocolError` follows `request_failed`, retains
  the decoded request ID, and is not classified as malformed envelope input.
- Focused daemon request, transport, and server tests: 82 passed.
- Full suite: 2136 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed; static search shows payload decoding centralized
  and each remaining socket `ProtocolError` catch scoped to frame read,
  envelope decode, or response encode.

## Publication

Daemon protocol error source separation was implemented in `d6f86a2`;
milestone publication is pending this goal update and push.

## Next Review Batch

After this boundary is complete, review broad exception scopes around
post-commit auxiliary work and response construction.
