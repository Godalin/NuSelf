# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make daemon readiness depend on actual worker liveness at the publication
boundary. Successfully spawning worker threads is insufficient when one exits
during startup; the process must abort startup rather than publish
`daemon/started` and accept requests with a dead subsystem.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory daemon startup, worker start, and readiness publication ordering.
2. Reproduce a worker exiting after successful spawn but before readiness.
3. Specify authoritative startup-health requirements.
4. Add a sealed supervisor check for every registered worker.
5. Place the check before `daemon/started` and request handling.
6. Run focused and full quality gates, commit by functional boundary, push, and
   confirm development-branch CI.

## Out Of Scope

- No automatic worker restart or replacement.
- No change to runtime health response schema.
- No continuous readiness revocation after startup; runtime health remains the
  authority for later failures.
- No change to worker start order or cleanup aggregation.
- No change to best-effort `started` audit persistence.

## Completion Evidence

- Worker `start()` returns after `thread.start()`, but a fast target may exit
  before all five daemon workers finish starting.
- `DaemonWorkerSupervisor.require_all_running()` now checks the complete sealed
  registration set against each owned lifecycle snapshot.
- Any registration that is not both `running` and alive raises typed
  `DaemonWorkerReadinessError` with stable worker/state details.
- `DaemonState` exposes that check and the server invokes it after all five
  starts but before `daemon/started` or request handling.
- The sealed registration set and `OwnedWorker.snapshot` provide authoritative
  startup-liveness evidence without adding parallel thread state.
- Regression tests prove unstarted and prematurely stopped workers reject
  readiness, while two live workers pass.
- Process-lifecycle tests prove readiness failure performs every worker cleanup,
  removes socket/PID metadata, and publishes neither `started` nor `stopped`.
- Focused daemon readiness tests: 76 passed.
- Full suite: 2164 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed.

## Publication

Worker-backed daemon readiness was implemented in `9729dae`; milestone
publication is pending this goal update, push, and development-branch CI.

## Next Review Batch

After this boundary is complete, review post-start health staleness semantics
and whether last-attempt timing is required.
