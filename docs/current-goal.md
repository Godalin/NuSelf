# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The daemon-side reason export job lifecycle has been extracted.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `daemon/reason_export.py` owns typed enqueue, pre-thread dependency
  preparation, manifest/progress inspection, single-job processing, failure
  persistence, retry timers, startup reconciliation, message-context
  activation, queue polling, and shutdown drain.
- `DaemonState` injects `ReasonExportWorker.enqueue` into `ChatAgent`, registers
  `ReasonExportWorker.run` with the shared supervisor, and retains only
  prepare/start plus stop/join composition.
- The stopping gate and lifecycle lock close enqueue before drain; a regression
  test proves a composition failure racing with shutdown cannot create a new
  retry timer.
- Recovery tests patch and inspect the owning module rather than daemon server
  internals.
- `daemon/server.py` decreased from 1116 to 582 lines and contains no export
  queue, timer, store, service, manifest, or progress implementation.
- Focused export/daemon/reason-output tests: 67 passed.
- Final full tests: 1270 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue daemon lifecycle composition review or resolve the REPL presentation
contract.
