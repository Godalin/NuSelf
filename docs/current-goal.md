# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Validate structured log timestamps as aware instants and order logs
chronologically rather than lexicographically.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit every timestamp source and log sorting point.
2. Specify aware ISO timestamps and the plain-legacy empty sentinel.
3. Parse and cache one instant during `LogEvent` construction.
4. Share one chronological sort key across full and incremental readers.
5. Verify offset-equivalent instants and invalid/naive timestamps.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Preserve the empty timestamp only for wrapped plain legacy lines.
- Preserve stable input order when timestamps identify the same instant.
- Keep timestamp corruption under existing record isolation diagnostics.

## Completion Evidence

- `LogEvent` parses and caches one aware `datetime` instant during construction;
  malformed, naive, and empty structured timestamps are rejected.
- The empty timestamp sentinel is available only to the internal wrapper for
  plain non-JSON legacy lines.
- Full reads and `InteractiveLogCursor` both use
  `LogEvent.chronological_key()`, comparing actual instants across offsets
  while preserving stable order for equal instants.
- Tests cover offset-induced lexical misordering, equal-instant stability,
  cross-component cursor order, invalid timestamps, and legacy behavior.
- Focused log, CLI, REPL activity, and daemon activity tests: `359 passed`.
- `.venv/bin/pytest -q`: `1539 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `855c2cf`.

## Next Review Batch

Audit duplicate event identity handling across rotated/full reads.
