# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close REPL Reason completion failure audit ownership so the UI caller no longer
constructs a Reason event outside the sealed Reason registry.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory dynamic completion failure owners, UI fallback behavior, event
   schemas, consumers, and tests.
2. Separate Chat thread completion diagnostics from Reason thread completion
   diagnostics despite their shared event name.
3. Update Reason, CLI, log, error, and development specs before implementation.
4. Register the Reason completion failure with a fixed message, degraded
   status, required error, and no redundant metadata.
5. Route the REPL completion loader through `run_reason_observed`.
6. Remove its direct generic observability import and caller-selected
   projection without compatibility aliases.
7. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No change to completion matching, display text, or repository reads.
- No change to the empty-suggestion fallback when loading fails.
- No change to Chat thread or archived-thread completion audit contracts.
- No promotion of completion failures into authoritative command failures.

## Completion Evidence

- Reason completion audit ownership completed in `82bb51f`.
- `reasoning/completion_load_failed` now belongs to the sealed Reason registry
  with a fixed message, warning/degraded projection, required error, and no
  metadata.
- REPL completion control flow now calls `run_reason_observed` and no longer
  imports generic observability or chooses audit presentation.
- Redundant `completion=reason_threads` metadata was removed without a
  compatibility alias; Chat completion contracts remain unchanged.
- Focused tests: 109 passed.
- Full suite: 2051 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Reason completion audit ownership was implemented in `82bb51f`; milestone
publication is pending this goal update and push.

## Next Review Batch

Close process-local log observer failure audit ownership: `logs.py` currently
constructs `daemon/log_observer_failed` directly, including free-form observer
and exception type metadata, outside a sealed infrastructure registry.
