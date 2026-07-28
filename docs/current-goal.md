# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make exception reporting unable to replace the failures it describes.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit event aggregation and compact exception-chain formatting.
2. Define one safe exception-text primitive for reporting boundaries.
3. Use it in event delivery and shared observability.
4. Remove the daemon request layer's duplicate chain formatter.
5. Verify broken exception stringification cannot replace original failures.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Exception objects and explicit cause/context links remain authoritative.
- Normal exception messages and compact-chain deduplication remain unchanged.
- Full traceback rendering remains outside normal diagnostics.

## Completion Evidence

- `safe_exception_message(...)` provides one non-raising exception-text
  primitive for diagnostic boundaries.
- Compact exception-chain formatting uses the safe primitive, preserves normal
  unique messages and cause/context rules, and falls back to the class name
  when an exception renderer fails.
- Runtime event aggregation retains the original failure object and emits a
  stable fallback even when its `__str__` raises.
- Daemon request errors now use the shared compact-chain formatter instead of
  a divergent private implementation; duplicate messages are removed as the
  error specification requires.
- Focused event, observability, and daemon suites: `76 passed`.
- Full test suite: `1624 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `6e70aae`.

## Next Review Batch

Continue reviewing error serialization and diagnostic privacy after exception
formatting is fail-safe and unified.
