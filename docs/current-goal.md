# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Persisted reason thread/step records now use a complete strict wire
schema; missing or malformed state cannot decode as empty/default state.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Every field emitted by reason thread/step serializers is required by the
  corresponding decoder.
- Nullable timestamps and confidence still accept explicit null values, but
  missing keys are invalid.
- Tracked-item and tool-log collections require lists containing only objects;
  mandates and evidence refs require lists containing only strings.
- Malformed collection members are rejected rather than filtered out, and
  boolean confidence values are rejected rather than coerced to `1.0`/`0.0`.
- Table-driven tests cover missing and malformed thread/step fields.
- Focused reason domain/repository/service/advancer tests: 106 passed.
- Final full tests: 1409 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit nested `TrackedItem` decoding and remaining domain decoders for
lossy coercion.
