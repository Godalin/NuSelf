# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close process-local log observer failure audit ownership so logging core uses
one sealed infrastructure contract without persisting callable or exception
type names.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory observer delivery, recursion suppression, diagnostic persistence,
   terminal warning fallback, consumers, metadata, and tests.
2. Keep observer failure distinct from daemon lifecycle and generic
   observability projection failures.
3. Update log, error, and development specs before implementation.
4. Define a sealed log infrastructure registry with one exact
   `daemon/log_observer_failed` contract.
5. Validate the fixed warning/error projection before direct recursive-safe
   persistence.
6. Remove callable identity and exception type metadata plus the unused
   observer parameter without compatibility aliases.
7. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No change to observer registration, nesting, order, or context isolation.
- No change to write-before-observe ordering or later-observer delivery.
- No change to observer suspension while writing its diagnostic.
- No change to the single terminal warning when diagnostic persistence fails.

## Completion Evidence

- Log observer failure audit ownership completed in `6a15634`.
- `LOG_INFRASTRUCTURE_AUDIT_REGISTRY` is sealed and owns the sole exact
  `daemon/log_observer_failed` definition.
- Observer delivery now supplies only the caught exception while logging core
  fixes the component, event, message, warning/error projection, error policy,
  empty metadata schema, and terminal fallback.
- Callable class and duplicate exception type metadata plus the unused
  observer reporter parameter were removed without compatibility aliases.
- Focused tests: 95 passed; final logging-core tests: 69 passed.
- Full suite: 2052 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Log observer failure audit ownership was implemented in `6a15634`; milestone
publication is pending this goal update and push.

## Next Review Batch

Review logging-core terminal warnings next. Lock cleanup, append rollback,
rotation, corrupt-record, and event-identity paths still construct independent
free-form warning strings and repeated field formatting without a sealed typed
warning taxonomy.
