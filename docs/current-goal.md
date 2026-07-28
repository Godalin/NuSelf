# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Daemon diagnostic project-root lookup now degrades only for an unowned
server adapter and no longer hides failures in owned request state.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `_request_project_root()` uses an explicit `NuSelfUnixServer` ownership
  check instead of calling the strict state accessor under `except Exception`.
- Owned server state supplies the diagnostic project root directly.
- An unowned server adapter returns `None` without reading structurally
  unrelated state.
- Unexpected owned-state access failure propagates instead of being silently
  erased.
- Focused daemon transport tests: 37 passed.
- Final full tests: 1379 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit remaining CLI/REPL and daemon broad exception boundaries, prioritizing
places that conflate expected domain failures with unexpected implementation
or infrastructure errors.
