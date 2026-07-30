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

The explicit schema-migration foundation is complete:

- the runtime accepts only schema v3 and performs no automatic migration;
- versioned v1→v2 and v2→v3 scripts live outside the runtime package;
- the operator script supports dry-run planning, exact targets, a consistent
  pre-migration backup, a cross-process lease, and one transaction per path;
- historical forward-only downgrade requests fail before mutation, while the
  contract requires both directions for every post-v3 migration;
- Pyright completed with 0 errors and 0 warnings, focused storage tests passed
  95 cases, the full suite passed 2432 tests, distributions built, and the
  wheel imported and reported its version from a clean uv environment.
