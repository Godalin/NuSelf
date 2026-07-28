# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Provide one typed best-effort log projection API and migrate reflection
scheduling so auxiliary evidence cannot change scheduler decisions.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory shared log fields and failure-diagnostic metadata.
2. Specify `write_observed_log_event(...)` as the auxiliary projection API.
3. Replace chat-local wrappers with the shared API.
4. Migrate every direct reflection-scheduler projection.
5. Verify uncertain writes cannot change reflection outcomes.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Authoritative callers retain direct `write_log_event(...)`.
- The observed API never retries its original event.
- A diagnostic uses the same component with stable failure identity and
  `audit_event` metadata.

## Completion Evidence

- `write_observed_log_event(...)` mirrors all typed log/correlation fields,
  returns `LogEvent | None`, and delegates failure to the non-recursive shared
  observability boundary without retrying the original event.
- Failure diagnostics use `audit_projection_failed`, retain caller-supplied
  diagnostic context, and always add the canonical `audit_event`.
- Chat adapters and the REPL retry marker now use the shared API without local
  lambda wrappers.
- Every reflection scheduler projection now uses the shared API; an unavailable
  audit store cannot change a successfully persisted reflection result.
- Focused observability, reflection, CLI, chat, and REPL tests: `383 passed`.
- `.venv/bin/pytest -q`: `1560 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `910a64d`.

## Next Review Batch

Migrate remaining direct reason, notification, and tool projections.
