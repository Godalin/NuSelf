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

The repair-aware Attention projection is complete:

- startup suppresses only a decode failure followed by a successful validated
  update for the exact same collection and record ID;
- failures after repair, failures for another record, and unidentified
  failures remain visible while historical logs remain intact;
- the real local authority starts without the obsolete 386-failure Attention
  block and still validates all 88 memory records;
- focused tests passed 6 cases, Pyright completed with 0 errors and 0 warnings,
  and the full suite passed 2431 tests.
