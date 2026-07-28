# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Daemon subsystem and worker-target composition has been extracted from
the process runner.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `daemon/state.py` owns request-facing services, config-derived intervals,
  ChatAgent/export wiring, notification adapter selection, concrete worker
  targets, supervisor registration, and worker-specific start/stop operations.
- `daemon/server.py` imports the state factory while retaining instance lock,
  PID/socket ownership, signal installation, startup order, server loop,
  cleanup ordering, and lifecycle failure aggregation.
- Business, request, export, and worker tests import `daemon.state` directly;
  process-instance tests still replace `server.DaemonState` as the runner
  factory injection point.
- The unused `DEFAULT_MEMORY_CURATOR_INTERVAL_SECONDS` constant was removed;
  config remains the only interval source.
- `daemon/server.py` decreased from 459 to 250 lines.
- Focused state/worker/export/instance tests: 55 passed.
- Final full tests: 1270 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue daemon lifecycle composition review or resolve the REPL presentation
contract.
