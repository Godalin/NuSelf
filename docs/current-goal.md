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

The compact schema-v5 authority is complete:

- v4 remains a frozen, valid historical identity with its two prefix indexes;
- reversible `v004_to_v005` removes those indexes, while v4→v3 now requires
  exported workspace state and removes both compact tables;
- runtime and migration validation enforce exact table, column, primary-key,
  strict-JSON, `WITHOUT ROWID`, and version-specific index identity;
- malformed-schema, rollback, size, workspace, and v3↔v5 round-trip
  regressions pass;
- the repository-local authority reports versions 1–5, 3654 domain records,
  93 workspace rows, no explicit secondary indexes, and `quick_check=ok`;
- its retained pre-v4 backup remains at schema v3 and passes `quick_check`;
  all 89 memory records remain valid;
- focused tests passed 159 cases, the full suite passed 2448 tests, Pyright
  reported 0 errors and 0 warnings, and the sdist/wheel plus clean Python 3.14
  wheel smoke test passed.
