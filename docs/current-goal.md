# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Memory curator action validation is strict, and any invalid generated
action defers the complete decision before dispatch.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Curator output and action models use strict types, forbid extra fields, limit
  tags to four, and constrain confidence from zero through one.
- Every action is converted to `MemoryAction` before dispatch; one invalid
  sibling rejects the complete generated decision.
- Mutation actions require non-blank title/body, normalized non-empty tags, a
  registered memory type, and no raw transcript body.
- Update actions require a non-empty target entry id.
- Confidence clamping is removed from parsing and candidate creation because
  invalid values no longer cross the typed boundary.
- Focused curator tests: 29 passed.
- Final full tests: 1430 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `f02ca22`.

## Next Review Batch

Strictly validate optimizer actions as a complete batch before candidate
dispatch.
