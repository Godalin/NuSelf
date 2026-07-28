# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make daemon readiness publication match actual service readiness.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit socket bind, PID publish, worker start, started audit, and request loop.
2. Define one ordered readiness boundary before requests can be accepted.
3. Publish `started` only after every worker starts successfully.
4. Publish successful `stopped` only for a daemon that reached readiness.
5. Keep started/stopped audit failure secondary to lifecycle decisions.
6. Verify partial worker failure, ordering, request visibility, and cleanup.
7. Run full quality gates, commit, and push.

## Out Of Scope

- Client status remains based on a successful typed ping response.
- PID remains diagnostic metadata, not a readiness signal.
- Worker-internal health degradation after startup remains separately reported.

## Completion Evidence

- `_run_owned_daemon()` now publishes `started` and marks readiness only after
  socket bind, PID publication, and all five worker starts succeed.
- The request loop begins strictly after readiness publication, so a successful
  typed ping cannot precede the authoritative server boundary.
- A partial worker-start failure runs every owned cleanup step but publishes
  neither `started` nor the matching successful `stopped` record.
- Successful `stopped` remains conditional on having reached readiness and on
  every owned cleanup step succeeding.
- Existing audit-failure coverage proves a failed `started` projection cannot
  undo readiness or suppress the later authoritative cleanup decision.
- Direct order tests cover PID-before-workers, all-workers-before-started,
  started-before-request, request-before-stopped, and partial-start failure.
- Focused daemon instance and server suites: `52 passed`.
- Full test suite: `1713 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through implementation commit `01f982c`.

## Next Review Batch

Review explicit ownership/readiness status modeling after server publication
order is authoritative.
