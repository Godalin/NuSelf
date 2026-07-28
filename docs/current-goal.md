# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Give Reflection audit events one closed, validated domain contract.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory Reflection audit producers and compare them with the domain spec.
2. Define reusable domain-audit registry and validation mechanics.
3. Register every Reflection-owned event with exact status/error/metadata rules.
4. Route scheduler and organizer writes through one Reflection audit adapter.
5. Keep persona and infrastructure failure events in their owning domains.
6. Verify unknown events and invalid payloads fail before the best-effort sink.
7. Run full quality gates, commit, and push.

## Out Of Scope

- No process-global registry containing every domain's audit events.
- No migration or rewriting of historical JSONL records.
- No change to Reflection scheduling, persistence, or scoring behavior.
- `persona_discussion` remains owned by the persona subsystem.
- Generic audit-projection failure events remain owned by observability.

## Completion Evidence

- The audit inventory found thirteen Reflection-owned events while the former
  domain table documented only six mixed-owner entries.
- `runtime.audit_definitions` now owns reusable audit identity, exact
  projection validation, duplicate rejection, lookup, and sealing semantics.
- Neutral component and severity types now live in `runtime.audit_types`, so
  definition infrastructure does not depend back on the persistent log sink.
- `reflection.audit` owns a sealed registry for all thirteen Reflection event
  names and their exact level, status, error, and metadata contracts.
- Scheduler and organizer producers now use one Reflection adapter; scattered
  Reflection component/event/level/status combinations have been removed.
- Unknown Reflection events and invalid payloads fail before the best-effort
  persistence sink, so producer bugs are not misreported as storage failures.
- Persona discussion writes remain persona-owned; generic projection-failure
  events remain observability-owned.
- Direct tests cover generic registry duplicate/seal/lookup behavior, all
  canonical Reflection schemas, unknown fields, unknown events, and pre-sink
  rejection.
- Focused audit, Reflection, observability, and log suites: `172 passed`.
- Full test suite: `1801 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

The Reflection audit-contract batch is awaiting its implementation commit.

## Next Review Batch

Review Reason output and export-worker audit schema ownership.
