# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make daemon startup failure and timeout reporting authoritative and actionable.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit readiness polling, child ownership, and every CLI start entrypoint.
2. Define one typed lifecycle failure for spawn, exit, and timeout.
3. Replace iteration-count waiting with an injectable monotonic policy.
4. Preserve latest status, exit code, and original spawn cause.
5. Project failed starts consistently without exposing raw process output.
6. Verify deadlines, early exits, safe messages, audits, and REPL survival.
7. Run full quality gates, commit, and push.

## Out Of Scope

- Shutdown escalation and timeout behavior are a later review batch.
- Startup does not tail or parse the raw process log for error messages.
- Server initialization and worker construction behavior remain unchanged.

## Completion Evidence

- `DaemonStartError` distinguishes `spawn_failed`, `process_exited`, and
  `timeout` while retaining the latest status, exit code, and explicit spawn
  cause.
- `DaemonStartupPolicy` validates positive finite timing and remains injectable
  for deterministic lifecycle tests.
- Readiness uses a monotonic deadline; every sleep and daemon ping is capped by
  the remaining budget so socket I/O cannot extend the wait silently.
- The raw process stream is never read for terminal diagnostics; CLI messages
  use one stable safe formatter while structured audits retain the sanitized
  exception chain.
- `start_daemon_observed()` owns requested, completed, and failed projections
  for explicit start, default startup, one-shot restart, and REPL restart.
- Early exit, timeout, spawn cause, deadline timing, audit metadata, default
  entrypoint failure, and interactive REPL survival have direct tests.
- Focused lifecycle, CLI, and daemon transport suites: `372 passed`.
- Full test suite: `1687 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is ready to publish through implementation commit `6871e22`.

## Next Review Batch

Review shutdown timeout, escalation ownership, and stale PID safety after
startup failure reporting is authoritative.
