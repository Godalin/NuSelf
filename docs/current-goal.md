# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Give every top-level CLI invocation a symmetric default-backend teardown that
runs after one-shot commands and after REPL cleanup.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit CLI, REPL, and daemon lifecycle nesting.
2. Specify the CLI storage teardown and failure precedence.
3. Run backend reset once at the outer CLI boundary.
4. Preserve primary exceptions and aggregate reset failures.
5. Verify normal, exceptional, and cleanup-failure paths.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep REPL transcript/curator cleanup ordered before storage teardown.
- Keep daemon-owned shutdown cleanup valid and reset idempotent.
- Do not reset storage during nested command dispatch.

## Completion Evidence

- `main()` runs one project-scoped `storage.default_backend.reset` after every
  completed or failed dispatch.
- REPL transcript and curator cleanup remain inside dispatch, so the outer
  storage reset runs after both.
- Successful reset preserves and re-raises the exact dispatch `BaseException`
  object with its traceback.
- Reset failure produces `CliLifecycleError` with the named shared
  `CleanupFailure`; a simultaneous dispatch failure is retained as
  `primary_error` and explicit cause.
- Focused CLI tests cover normal return, `SystemExit`, and dual failure.
- `.venv/bin/pytest -q`: `1479 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `e01d67b`.

## Next Review Batch

Make the dev storage diagnostic explicitly close the backend it creates.
