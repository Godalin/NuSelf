# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make daemon shutdown bounded without trusting stale PID metadata.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit shutdown polling, request failure, PID use, and instance-lock ownership.
2. Make instance-lock release the authoritative stop completion boundary.
3. Remove unsafe signal escalation based only on PID metadata.
4. Share one injectable monotonic wait policy across startup and shutdown.
5. Unify stop/restart audit projections across CLI and REPL surfaces.
6. Verify stale PID safety, request ambiguity, deadlines, and REPL survival.
7. Run full quality gates, commit, and push.

## Out Of Scope

- Force termination remains an explicit operator action outside this CLI.
- Server-owned worker cleanup and signal-handler behavior remain unchanged.
- Startup readiness and failure behavior remain unchanged.

## Completion Evidence

- `DaemonWaitPolicy` provides one validated positive finite monotonic policy
  type for startup and shutdown, with separate default instances.
- Stop completion requires both failed readiness and released project instance
  lock; a real contended-lock test proves cleanup ownership is observed.
- PID metadata is populated only after a successful project ping and is never
  used for signal escalation; a valid stale PID remains untouched and cannot
  trigger shutdown or process signaling.
- `DaemonStopError` distinguishes explicit request rejection, ownership-check
  failure, and ownership-release timeout while retaining status and cause.
- A lost shutdown acknowledgement remains attached while lifecycle polling
  continues; every request, ping, and sleep is capped by the shared deadline.
- The instance lock path now belongs to shared `RuntimePaths`, so server and
  lifecycle clients cannot drift to different ownership files.
- `stop_daemon_observed()` owns requested, completed, and failed projections
  for stop and restart; one-shot and REPL failure behavior have direct tests.
- Focused lifecycle, CLI, transport, config, and instance suites: `408 passed`.
- Full test suite: `1705 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through implementation commit `30822f1`.

## Next Review Batch

Review runtime metadata cleanup and crash recovery after shutdown no longer
trusts reusable PID numbers.
