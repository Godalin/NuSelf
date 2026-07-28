# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. `nuself.runtime.context` is now the only public and internal
correlation-context API.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `nuself.logs` reads `current_runtime_context()` directly and no longer
  defines `LogContext`, `current_log_context()`, or `log_context()`.
- Reason scheduling, chat turns, and persona consultation use the neutral
  runtime API; no production or test caller imports a logging-owned context
  name.
- The logging spec defines logs as a consumer of context while keeping
  process-local observers separate from serializable correlation identity.
- Existing persisted `LogEvent` fields and intentional per-event overrides are
  unchanged.
- Focused runtime/log/chat/reason/persona/daemon/notification tests: 452 passed.
- Final full tests: 1273 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit direct correlation overrides and event-to-audit projection after context
API ownership is singular.
