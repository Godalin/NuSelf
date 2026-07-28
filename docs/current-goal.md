# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Manual memory intake accepts only the complete strict generated schema
and rejects invalid confidence or importance instead of repairing it.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Intake output uses strict types, forbids extra fields, and requires type,
  title, tags, confidence, and importance without generated defaults.
- Generated tags require one through four items. Confidence and importance are
  constrained from zero through one at the typed boundary.
- Empty normalized titles/tags and unregistered types remain rejected.
- Confidence and importance clamping is removed; invalid values fail intake.
- Focused intake tests: 15 passed.
- Final full tests: 1447 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

Push is authorized; completed review batches are published immediately after
their validated commit.

## Next Review Batch

Audit remaining prompted-JSON subsystem boundaries and prioritize migration to
framework-native structured output.
