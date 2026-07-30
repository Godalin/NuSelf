# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

No active implementation goal.

## Active Branch

None.

## Ordered Work

None.

## Out Of Scope

None.

## Completion Evidence

The daemon deadlock and restart goal is complete:

- chat turns no longer hold the shared SQLite transaction lock across
  LangGraph/model/tool execution; the final short transaction rechecks the raw
  thread snapshot before commit;
- graceful stop/restart has a 30-second ownership-release budget while each
  control probe remains capped at two seconds;
- the previously deadlocked PID `91335` was sampled, confirmed stuck in the
  SQLite/thread-lock cycle, and replaced once after explicit approval;
- a real restart completed from PID `90807` to PID `91116`; process inspection
  confirmed exactly one NuSelf daemon and health reported all five owned
  worker threads alive with zero failures;
- focused regression tests passed 161 cases, Pyright completed with 0 errors
  and 0 warnings, and the full suite passed 2425 tests.
