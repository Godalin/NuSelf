# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Every persisted reason step now carries an explicit terminal decision;
incomplete records are rejected instead of silently treated as `continue`.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `ReasoningStep.from_wire()` requires `terminal_status` and validates it
  against the terminal-status enum.
- `terminal_reason` is required even when an ordinary continuing step stores
  the empty string.
- In-memory construction defaults remain available and every serializer writes
  both fields.
- Regression tests reject records missing either half of the terminal
  decision.
- Focused reason domain/repository/service/advancer tests: 79 passed.
- Final full tests: 1382 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit remaining optional persisted reason fields against their actual
introduction and migration contracts.
