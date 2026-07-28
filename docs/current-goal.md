# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The Reason agent invocation ownership batch is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- One `ReasonAdvancer` serializes its shared LangGraph graph and middleware
  capture buffer without imposing a global lock.
- Concurrent reasoning threads retain isolated runtime context and tool logs.
- Invocation ownership is released after an exception.
- Focused Reason and middleware tests: 46 passed.
- Full tests: 1241 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing shared callback and event ownership after agent invocation
isolation.
