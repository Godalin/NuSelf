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

The interactive-attention goal is complete:

- the governing CLI specification defines startup and per-turn notice
  selection, grouping, safety, and non-interference;
- focused notice, activity, and lifecycle tests pass;
- `uv run --locked pyright` completed with 0 errors and 0 warnings;
- `uv run --locked pytest -q` completed with 2394 passing tests;
- `uv build` produced the v0.3.1 sdist and wheel;
- the wheel installed into a clean Python 3.14 environment, imported
  `nuself.cli` and `nuself.cli.repl.notices`, and reported `nuself 0.3.1`.

The final pushed commit remains subject to the normal six-platform GitHub CI
gate; a failure reopens the goal.
