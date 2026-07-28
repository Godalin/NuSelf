# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Chat-turn lifecycle is now a production `EventPublisher` boundary whose
completed event proves the thread update was durably saved.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `ChatAgent` accepts an instance-scoped publisher; `DaemonState` injects its
  shared publisher and standalone agents compose an audit-backed publisher.
- New turns publish `turn.started`; `turn.completed` is emitted only after
  `ThreadStore.update()` saves; graph/load/persistence failures emit
  `turn.failed` and re-raise the original exception; idempotent retries emit
  only `turn.reused`.
- A synchronous completed-event subscriber successfully reads the saved
  assistant message, while a forced save failure proves completed is absent.
- Event, audit, and daemon live-activity projections retain the same message ID
  plus request/thread/turn correlation.
- Subscriber failures neither replace a completed response nor mask the
  original graph failure.
- Worker and chat lifecycle owners share `publish_observed_event(...)`;
  aggregate delivery diagnostics retain subscriber exception details.
- Focused chat/daemon/runtime/log/REPL tests: 436 passed.
- Final full tests: 1283 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit remaining direct correlation overrides after chat lifecycle is unified.
