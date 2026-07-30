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

The v0.3.1 CLI exit-code typing correction is complete:

- `CliExitCode` is the single `IntEnum` for statuses `0` through `5`;
- readiness, entrypoint, chat transport, dispatch, and REPL infrastructure use
  named enum members instead of raw process-status literals;
- the public shell values and existing failure classifications are unchanged;
- Pyright completed with 0 errors and 0 warnings;
- the full suite completed with 2403 passing tests, followed by 51 passing
  focused CLI/REPL tests after the final infrastructure edits.
