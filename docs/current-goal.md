# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make daemon lifecycle audit events closed, typed, and schema-validated.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory every server and CLI lifecycle audit event and payload.
2. Define one immutable event registry with projection defaults.
3. Validate exact metadata fields and value types per event.
4. Model restart failure's start/stop schemas as explicit branches.
5. Migrate producers away from free-form message/level/status arguments.
6. Prove schema errors fail before the best-effort persistence boundary.
7. Run full quality gates, commit, and push.

## Out Of Scope

- Persisted event names and valid payload meanings remain unchanged.
- Lifecycle transition behavior and CLI output remain unchanged.
- Sink failures remain observable and secondary to lifecycle decisions.

## Completion Evidence

- Inventory identified 13 persisted lifecycle events across daemon ownership,
  server readiness/recovery, and CLI start/stop/restart orchestration.
- `daemon.audit` now owns an immutable registry whose definitions fix each
  event's message, level, status, error policy, and metadata validator.
- `write_lifecycle_audit()` accepts only the closed event literal plus error,
  metadata, and project root; producers cannot override projection defaults.
- Exact validators reject missing, extra, non-string, incorrectly typed, or
  semantically inconsistent metadata fields.
- Start/stop completion validation couples outcome to `changed` and enforces
  the operation's final phase; restart completion validates both phases.
- `restart_failed` selects one strict schema from its explicit `start` or
  `stop` stage and rejects mixed or unknown variants.
- Required/forbidden error policies are validated alongside event metadata.
- Unknown events and schema violations raise before the best-effort sink, while
  valid-record persistence failure keeps the existing secondary semantics.
- Every server and CLI lifecycle producer now supplies only registered event
  data; local message, level, and status arguments were removed.
- Direct tests prove registry immutability, unknown-event rejection, exact
  fields and types, semantic outcome checks, error policy, restart variants,
  pre-sink failure ordering, and registered projection defaults.
- Focused daemon lifecycle/audit and CLI suites: `402 passed`.
- Full test suite: `1742 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through implementation commit `d4aca10`.

## Next Review Batch

Review the relationship between persisted audits and in-process runtime event
definitions after lifecycle audit schemas are authoritative.
