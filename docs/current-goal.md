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

The v0.3.1 readiness and failure-disposition goal is complete:

- every executable CLI parser declares a typed readiness requirement;
- missing initialization and model configuration fail before storage, daemon,
  or REPL side effects with actionable scoped commands and exit status `3`;
- temporary daemon/transport failures use exit status `4`, while interactive
  retry retains the original message, thread, and `turn_id`;
- `uv run --locked pyright` completed with 0 errors and 0 warnings;
- `uv run --locked pytest -q` completed with 2402 passing tests;
- `uv build` produced the v0.3.1 sdist and wheel;
- the wheel installed into a clean Python 3.14 environment, imported the new
  readiness module, reported `nuself 0.3.1`, and passed real missing-init and
  missing-model startup smoke tests without creating state or starting daemon
  runtime files.

The final pushed commit remains subject to the normal six-platform GitHub CI
gate; a failure reopens the goal.
