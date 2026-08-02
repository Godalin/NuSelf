# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle — no active implementation goal.

## Objective

No active objective.

## Next Steps

1. Define the next objective, exclusions, ordered steps, and completion evidence
   before implementation.

## Exclusions

- Do not start non-trivial implementation while this goal is idle.

## Last Verification

- `src/nuself` now contains only `__init__.py` as a Python file. Settings and
  scope belong to `config`; endpoints to `agent`; clock and handles to
  `runtime`; filesystem primitives to `storage`; evaluation to `evaluation`;
  release checks to repository-only `scripts` tooling.
- Old flat imports and compatibility modules are absent. Package roots remain
  empty, and a structural test enforces the production-root boundary.
- Full Pyright reports 0 errors and 0 warnings. Full default pytest passes.
  NuSelf 0.3.1 source and wheel builds succeed; wheel inspection contains the
  new owners and none of the old flat modules or release tooling. A locked-
  dependency smoke test imports the owners directly from the wheel zip.
