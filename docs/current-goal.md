# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make runtime and persisted event identities stable and evolution-safe.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory event names, ownership, envelope versions, and historical readers.
2. Define shared lexical rules for producers, runtime events, and audit events.
3. Define wire-version versus semantic-contract evolution policy.
4. Enforce identities when definitions and new log records are constructed.
5. Preserve explicitly supported legacy JSONL reads without rewriting history.
6. Verify invalid identities, valid domain extensions, and version boundaries.
7. Run full quality gates, commit, and push.

## Out Of Scope

- No version-2 runtime envelope or persisted-record migration.
- No global registry for every direct domain audit event.
- No merging of runtime publication and persisted audit delivery.
- No compatibility aliases for invalid new identities.

## Completion Evidence

- Runtime envelope versioning is now explicitly limited to the common wire
  shape; it cannot stand in for event payload or semantic versioning.
- Breaking runtime-event contracts require a new registered event identity;
  breaking direct-audit semantics require a new stable audit slug.
- `runtime.identities` owns the lexical grammar shared by runtime definitions,
  direct audit construction, persisted projections, and lifecycle definitions.
- Runtime producers accept one lowercase slug; runtime event names require at
  least two dotted slug segments; direct audit names accept exactly one slug.
- `RuntimeEventDefinition` and `DaemonLifecycleAuditDefinition` reject invalid
  identities during construction, before registry composition or delivery.
- Direct audit construction rejects dotted runtime names, while persisted
  runtime projections retain valid dotted names including domain extensions
  such as `reason.output.export`.
- Existing legacy JSONL records still use the explicit absent-identity path;
  no historical record is rewritten or silently reclassified.
- Focused runtime-event, lifecycle-audit, and log suites: `121 passed`.
- Full test suite: `1769 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is ready to publish through implementation commit `97fe04d`.

## Next Review Batch

Review whether all direct domain audit schemas have explicit owning contracts.
