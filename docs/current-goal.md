# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close shared observability sink-failure terminal warning ownership so fallback
diagnostics use one fixed infrastructure identity and exact safe fields.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory every sink-failure warning consumer, dynamic field, exception
   diagnostic, redaction path, stacklevel, and outcome-preservation test.
2. Separate the fixed infrastructure warning identity from the failed business
   audit component/event.
3. Update runtime-infrastructure, log, error, and development specs first.
4. Define one sealed `runtime/observability_sink_failed` warning contract with
   exact component, event, observed-error chain, and sink-error fields.
5. Route `report_observed_failure` through the shared registered renderer
   without changing persistence attempts or result/exception preservation.
6. Remove direct warning interpolation and redundant local final redaction
   without compatibility aliases.
7. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No change to primary audit construction, metadata sanitization, or write
  attempts.
- No retry or recursive structured diagnostic after sink failure.
- No change to caller return values, raised primary exceptions, or fallback
  decisions.
- No migration of tool middleware or daemon process-log warnings in this batch.

## Completion Evidence

- Observability sink-failure warning ownership completed in `50dc7de`.
- `OBSERVABILITY_TERMINAL_WARNING_REGISTRY` is sealed and owns the single fixed
  `runtime/observability_sink_failed` definition with four exact ordered
  fields.
- `report_observed_failure` no longer calls `emit_runtime_warning`, constructs
  a dynamic warning identity, or performs local final redaction.
- The observed error retains its compact chain while the sink error excludes
  active primary context, eliminating duplicate primary diagnostics.
- Focused tests: 167 passed.
- Full suite: 2066 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Observability sink-failure warning ownership was implemented in `50dc7de`;
milestone publication is pending this goal update and push.

## Next Review Batch

Close agent tool middleware terminal warning ownership next.
`agent/middleware.py` still has two caller-formatted warning variants for a
failed tool-log callback with and without a failed failure reporter.
