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

Schema v4 and the compact workspace layout are complete:

- all 3654 repository-local domain records migrated into the unified records
  table and remain readable through all 16 collections;
- 93 legacy workspace/persona rows and 277 reason export files moved into the
  main authority and `exports/reason`;
- the verified legacy `workspaces/` tree is gone; one valid schema-v3 database
  backup remains under `.nuself/backups`;
- `PRAGMA quick_check` returned `ok`, all 89 memory records validate, and the
  v3 database backup still reports schema version 3;
- Pyright completed with 0 errors and 0 warnings, focused tests passed 179
  cases, and the full suite passed 2439 tests;
- the 0.3.1 sdist and wheel built successfully, and the wheel passed a clean
  Python 3.14 import and CLI smoke test.
