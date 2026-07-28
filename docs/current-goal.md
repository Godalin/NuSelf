# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make daemon runtime metadata recovery explicit and ownership-safe.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit stale socket/PID creation, publication, cleanup, and crash windows.
2. Define one lock-owned recovery boundary for both metadata resources.
3. Attempt all stale cleanup and retain every recovery failure.
4. Publish PID only after Unix socket binding succeeds.
5. Observe successful recovery without exposing runtime contents.
6. Verify contention, bind failure, hard-crash residue, and cleanup aggregation.
7. Run full quality gates, commit, and push.

## Out Of Scope

- Instance-lock implementation and shutdown waiting remain unchanged.
- Recovery does not delete the stable instance-lock file.
- Durable business-state recovery remains owned by each subsystem.

## Completion Evidence

- `_reconcile_stale_runtime_metadata()` runs inside the lock-owned daemon
  boundary and independently removes stale socket and PID resources.
- `DaemonRuntimeRecoveryError` retains every named reconciliation failure and
  chains the first root error; normal owned cleanup still runs afterward.
- Successful crash recovery emits one best-effort
  `runtime_metadata_recovered` audit containing only socket/PID booleans.
- PID publication moved inside the successfully bound Unix-server context and
  still uses the crash-durable atomic text writer.
- Bind failure cannot publish a PID; PID-publication failure stops before
  workers start and removes the already-bound socket.
- A contended starter still returns before recovery and preserves the active
  owner's socket and PID unchanged.
- Recovery success, dual failure, audit failure, bind ordering, publication
  failure, and cleanup behavior have direct tests.
- Focused daemon instance, server, lifecycle, config, and transport suites:
  `137 passed`.
- Full test suite: `1711 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through implementation commit `01f982c`.

## Next Review Batch

Review daemon readiness publication and client observation after crash recovery
has one explicit lock-owned boundary.
