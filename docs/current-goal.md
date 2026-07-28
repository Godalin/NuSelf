# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Distinguish missing legacy `LogEvent` fields from present-but-corrupt fields
without silently coercing evidence to `None`.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit local construction, record decoding, and reader skip behavior.
2. Specify legacy absence versus malformed presence.
3. Validate all required and optional fields in `LogEvent`.
4. Require new envelope identity fields to appear as a consistent pair.
5. Verify corrupt records are skipped without hiding healthy or legacy lines.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Preserve readable pre-envelope records with both identity fields absent.
- Preserve plain non-JSON legacy line wrapping.
- Keep the reader's record-isolation policy: one corrupt line does not hide
  healthy lines.

## Completion Evidence

- `LogEvent.__post_init__()` now validates required identity, level/component,
  paired envelope identity, optional scalar types, non-negative duration, and
  strict metadata for both local and decoded construction.
- `LogEvent.from_record()` uses field-aware strict decoders; invalid present
  values no longer collapse to `None`, and booleans are rejected as integers.
- Records are legacy only when both `event_id` and `schema_version` are absent
  or null; partial or unsupported identity is corrupt.
- Tests cover every formerly coerced optional field, partial envelope identity,
  genuine legacy decoding, and reader isolation of corrupt lines.
- Focused log, CLI, TUI, and REPL activity tests: `365 passed`.
- `.venv/bin/pytest -q`: `1532 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `dd0e288`.

## Next Review Batch

Audit log-reader diagnostics for isolated corrupt structured records.
