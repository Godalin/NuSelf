# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make daemon status observation single-use, reusable, and uniformly surfaced.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit every status call and identify duplicate observations per CLI decision.
2. Define explicit same-decision snapshot reuse without global caching.
3. Validate reused snapshots belong to the requested runtime project.
4. Reuse the default entrypoint snapshot when starting the daemon.
5. Centralize CLI status observation and safe failure reporting.
6. Cover REPL status failure and prove commands do not duplicate observation.
7. Run full quality gates, commit, and push.

## Out Of Scope

- Status remains an instantaneous observation, not a lease or durable fact.
- Start/stop polling always takes fresh snapshots after the initial decision.
- No process-global, time-based, or cross-command status cache is introduced.

## Completion Evidence

- Status-call audit found one duplicate default-launch observation and one REPL
  error path that bypassed the shared safe CLI boundary.
- `lifecycle.start(initial_status=...)` reuses only an explicitly supplied
  same-decision snapshot and rejects socket/PID paths from another project
  before creating runtime directories.
- Startup polling after the initial decision remains fresh, and daemon instance
  locking remains the authoritative competing-start race boundary.
- The default launcher now passes its initial stopped snapshot into startup, so
  that command decision performs one initial typed ping and ownership probe.
- `cli.daemon_status.observe_daemon_status()` is the single status/error
  boundary used by daemon commands, system checks, launch entrypoints,
  interactive headers, and REPL `:dev status`.
- Status inspection failure is rendered once with the stable safe message;
  internal cause details remain absent from CLI output and the REPL stays alive.
- Tests patch the real `nuself.daemon.lifecycle` owner rather than depending on
  an incidental re-export from the CLI composition root.
- Direct tests prove snapshot reuse, cross-project rejection, one observation
  per default launch decision, and safe REPL status failure.
- Focused lifecycle and CLI suites: `363 passed`.
- Full test suite: `1726 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is ready to publish through implementation commit `b0b81ad`.

## Next Review Batch

Review lifecycle transition result types and audit projection semantics.
