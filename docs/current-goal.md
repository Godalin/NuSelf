# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close logging-core terminal warning ownership so every non-persisting fallback
uses one sealed typed taxonomy and one credential-safe renderer.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory all logging-core terminal warning producers, fields, control-flow
   outcomes, safety paths, consumers, and tests.
2. Cover lock cleanup, append rollback, rotation, observer diagnostic failure,
   corrupt-record isolation, and event-identity conflict as six distinct
   definitions.
3. Update log, error, runtime-infrastructure, and development specs first.
4. Define reusable sealed terminal-warning definitions with exact ordered
   fields, validators, fixed suffixes, and one redacting renderer.
5. Route every logging-core warning through one sealed registry without
   changing primary outcomes or stacklevel ownership.
6. Remove free-form warning construction and unsafe direct corruption-error
   rendering without compatibility aliases.
7. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No structured-log write or retry from terminal warning paths.
- No change to append/rollback/rotation or read reconciliation decisions.
- No change to exception propagation, returned lifecycle errors, or observer
  delivery.
- No expansion to non-logging warning producers in this batch.

## Completion Evidence

- Logging-core terminal warning ownership completed in `06820f6`.
- `runtime.warning_definitions` now owns reusable duplicate-safe sealed
  definitions, exact-field validation, ordered single-line rendering,
  credential redaction, and a non-raising render-failure fallback.
- `LOG_TERMINAL_WARNING_REGISTRY` contains exactly six definitions covering
  every logging-core terminal warning producer.
- `logs.py` no longer calls `emit_runtime_warning` or interpolates terminal
  warning strings directly; corrupt-record errors use fail-safe diagnostics.
- Focused tests: 104 passed; final warning/log tests: 82 passed.
- Full suite: 2065 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Logging-core terminal warning ownership was implemented in `06820f6`; milestone
publication is pending this goal update and push.

## Next Review Batch

Close the shared observability sink-failure terminal warning next.
`runtime/observability.py` still interpolates caller component/event and two
exception chains directly instead of resolving a sealed typed warning
definition.
