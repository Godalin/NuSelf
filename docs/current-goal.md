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

The v0.3.1 interactive-startup blocking fix is complete:

- thread snapshot reads no longer acquire the per-thread mutation lock or open
  a SQLite write transaction;
- a cross-process regression test holds both the mutation lock and
  `BEGIN IMMEDIATE` while `load()` returns the last committed state promptly;
- real `uv run --locked nuself --local` startup displayed the banner and
  prompt immediately against the same daemon that reproduced the block;
- Pyright completed with 0 errors and 0 warnings;
- the full suite completed with 2404 passing tests.
