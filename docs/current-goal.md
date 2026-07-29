# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close daemon operational audit ownership so worker join timeout and lifecycle
cleanup failure use one exact validated contract.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory worker join timeout and daemon cleanup failure producers,
   exception types, metadata, ordering, and consumers.
2. Decide whether the two process-level records belong beside lifecycle
   definitions or in one dedicated daemon operations registry.
3. Update error, runtime-infrastructure, log, and development specs before
   implementation.
4. Define one sealed daemon operations audit registry with fixed messages and
   exact per-event metadata.
5. Route worker/server failure paths through the shared adapter without
   changing raised exceptions or cleanup ordering.
6. Remove raw `report_observed_failure` calls, free-form messages/defaults,
   and compatibility aliases.
7. Run focused and full quality gates, commit by functional boundary, and
   push.

## Out Of Scope

- No change to worker thread start/stop/join mechanics.
- No change to lifecycle cleanup ordering or exception aggregation.
- No conversion of primary join/cleanup failures into best-effort success.
- No change to request, transport, or lifecycle transition audit contracts.

## Completion Evidence

- Daemon transport audit ownership completed in `52afe43`.
- Socket read, unexpected dispatch, response encoding, and response delivery
  failures now use one sealed transport registry.
- `socket_server.py` no longer constructs failure messages or projection
  defaults.
- Undecoded requests no longer persist the internal `unknown` sentinel as
  correlation identity.
- Initial next-batch inspection finds raw daemon operations events for
  `thread_timeout` and `shutdown_cleanup_failed`.
- Focused tests: 55 passed.
- Full suite: 2029 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Daemon transport audit ownership was implemented in `52afe43`; milestone
publication is pending this goal update and push.

## Next Review Batch

Continue shared handler/log/message infrastructure review after daemon
operational audit ownership is verified and published.
