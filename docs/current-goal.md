# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The deferred callback context-propagation review batch is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `bind_runtime_context()` captures one immutable context and restores the
  invoker after success or failure.
- Interactive sends receive an exact thread/turn/client context without stale
  ambient identity.
- Transcript capture distinguishes chat-path presentation ownership from
  inherited correlation.
- Focused tests: 324 passed.
- Full tests: 1205 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit remaining direct thread/context primitives outside runtime ownership.
