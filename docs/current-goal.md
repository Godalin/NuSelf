# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Sanitize every persisted audit projection at the canonical log sink.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit ordinary audit metadata and observed-failure producers.
2. Identify the single runtime-envelope-to-`LogEvent` persistence boundary.
3. Define recursive field privacy rules without weakening JSON validation.
4. Sanitize message, error, and metadata at the canonical log projection.
5. Verify direct audit, runtime-event projection, observers, and immutability.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Non-credential domain content such as topics and discussion traces remains
  governed by its subsystem contract.
- Invalid non-JSON diagnostic values still fail strict validation and enter the
  existing terminal-warning fallback.
- Sanitization never mutates caller-owned metadata or runtime envelopes.

## Completion Evidence

- `sanitize_diagnostic_metadata(...)` recursively copies mappings and
  sequences, redacts credential text in ordinary strings, and replaces values
  under sensitive snake-case, kebab-case, camelCase, or dotted keys.
- The runtime-envelope-to-`LogEvent` projection sanitizes every persisted
  audit and runtime-event message, error, and metadata field before both
  observer delivery and disk append.
- `report_observed_failure(...)` retains defense-in-depth sanitization before
  constructing its audit envelope.
- Caller-owned nested containers and source runtime envelopes remain unchanged.
- Unsupported objects and non-string mapping keys are not coerced or rendered;
  strict `LogEvent` JSON validation still fails into the existing non-raising
  terminal-warning path.
- Tests cover direct audits, runtime-event projections, observer delivery,
  nested sensitive keys, embedded query credentials, sequences, camelCase
  labels, input immutability, persisted output, and invalid objects.
- Focused logging, runtime-event, and observability suites: `106 passed`.
- Full test suite: `1651 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is ready for publication through `7040784`.

## Next Review Batch

Review privacy ownership for non-log durable trace and export artifacts after
all persisted audit projections are protected centrally.
