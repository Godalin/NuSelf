# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make isolated corrupt structured log records observable without recursive
logging, warning floods, or payload disclosure.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit full-reader and incremental-cursor parse paths.
2. Specify a terminal payload-safe corruption diagnostic.
3. Aggregate corrupt records once per file read batch.
4. Share the diagnostic boundary across full and incremental reads.
5. Verify warnings cannot escape or expose raw log content.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Preserve plain non-JSON legacy lines without warning.
- Do not append diagnostics to any structured log.
- Do not include raw lines, absolute paths, or arbitrary record values.

## Completion Evidence

- `_parse_log_line()` reports structured-record schema failures through an
  injected collector while preserving plain non-JSON legacy behavior.
- Full reads and incremental `_read_log_path()` batches aggregate failures and
  call the non-raising terminal warning boundary once per affected file/batch.
- Diagnostics contain only component, basename, count, and the first schema
  error type/message; tests prove private record content and absolute paths are
  absent.
- Cursor offsets prevent repeat warnings after a corrupt line is consumed, and
  warning filters promoted to errors cannot fail the read.
- Focused log, CLI, and REPL activity tests: `350 passed`.
- `.venv/bin/pytest -q`: `1534 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `bd5f4e4`.

## Next Review Batch

Audit timestamp validation and chronological ordering invariants.
