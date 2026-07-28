# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Protect nested observed-failure metadata at the shared persistence boundary.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit every observed-failure and failure-metadata producer.
2. Distinguish safe identifiers from arbitrary nested diagnostic context.
3. Define recursive metadata privacy rules without weakening JSON validation.
4. Sanitize all shared observed-failure persistence paths centrally.
5. Verify sensitive keys, embedded credentials, immutability, and invalid types.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Ordinary successful audit metadata remains governed by its domain contract.
- Invalid non-JSON diagnostic values still fail strict validation and enter the
  existing terminal-warning fallback.
- Sanitization never mutates caller-owned metadata.

## Completion Evidence

- `sanitize_diagnostic_metadata(...)` recursively copies mappings and
  sequences, redacts credential text in ordinary strings, and replaces values
  under sensitive snake-case, kebab-case, camelCase, or dotted keys.
- `report_observed_failure(...)` applies the sanitizer at the central
  persistence boundary, covering direct reports, best-effort operations,
  observed event publication, and audit-projection failure metadata.
- Caller-owned nested containers remain unchanged.
- Unsupported objects and non-string mapping keys are not coerced or rendered;
  strict `LogEvent` JSON validation still fails into the existing non-raising
  terminal-warning path.
- Tests cover nested sensitive keys, embedded query credentials, sequences,
  camelCase labels, input immutability, persisted output, and invalid objects.
- Focused observability, logging, chat, daemon, reflection, persona, and reason
  suites: `295 passed`.
- Full test suite: `1649 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `0f2cb13`.

## Next Review Batch

Review ordinary audit metadata ownership separately after failure metadata is
protected centrally.
