# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close agent tool middleware terminal warning ownership so callback and failure
reporter failures use two exact sealed contracts.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory outcome construction, log callback, failure reporter, warning
   fallback, redaction, and primary tool semantics.
2. Separate missing-reporter callback failure from reporter failure as two
   exact terminal states.
3. Update agent-tools, error, runtime-infrastructure, and development specs.
4. Define a sealed two-event agent middleware warning registry with exact safe
   error fields and no tool payload facts.
5. Route both warning branches through registered rendering without changing
   callback ordering or result/exception preservation.
6. Remove direct `emit_runtime_warning` and free-form interpolation without
   compatibility aliases.
7. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No change to tool execution, cache, capture ordering, or outcome identity.
- No hidden tool retry after projection failure.
- No tool name, arguments, result, or tool exception payload added to warning
  metadata beyond the safe callback diagnostics.
- No migration of daemon process-log warnings in this batch.

## Completion Evidence

- Agent middleware terminal warning ownership completed in `ec9a92a`.
- `AGENT_MIDDLEWARE_WARNING_REGISTRY` is sealed and owns the exact
  callback-failed and failure-reporter-failed definitions.
- Middleware no longer calls `emit_runtime_warning` or interpolates fallback
  strings; registered rendering owns both credential-safe projections.
- Tests prove both reporter states preserve the successful `ToolMessage`,
  redact both diagnostics, and expose no tool payload facts.
- Focused tests: 56 passed.
- Full suite: 2068 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Agent middleware terminal warning ownership was implemented in `ec9a92a`;
milestone publication is pending this goal update and push.

## Next Review Batch

Close daemon process-log rotation warning ownership next. It is now the only
production domain call site that invokes `emit_runtime_warning` directly.
