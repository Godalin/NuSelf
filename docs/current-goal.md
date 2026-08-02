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

- The opt-in live API model/capability matrix lives in
  `tests/live/matrix.py`; `src/nuself/live_testing.py` is absent and no
  compatibility module remains.
- Full Pyright reports 0 errors and 0 warnings. The matrix and structural
  boundary tests pass, as does the complete default pytest suite.
- NuSelf 0.3.1 source and wheel builds succeed. Wheel inspection confirms no
  `live_testing` module or `tests/live` content is shipped.
