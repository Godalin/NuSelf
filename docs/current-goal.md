# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Remove parallel auxiliary-log wrappers so every non-authoritative structured
log uses the shared typed observed-log projection boundary.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory `run_observed_best_effort(lambda: write_log_event(...))` callers.
2. Confirm which callers are log projections and which are other side effects.
3. Route every auxiliary structured log through `write_observed_log_event`.
4. Preserve domain-specific failure event names and diagnostic metadata.
5. Add an architecture guard against reintroducing the parallel composition.
6. Run full quality gates, commit, and push.

## Out Of Scope

- `run_observed_best_effort` remains the boundary for non-log secondary effects.
- Authoritative log persistence continues to use `write_log_event` directly.
- Existing event names, correlation fields, and degradation behavior remain
  unchanged; shared failure metadata consistently includes `audit_event`.

## Completion Evidence

- Domain lifecycle, request, approval, curator, reflection, chat/persona, and
  reason-tool audit paths call `write_observed_log_event(...)` directly.
- `run_observed_best_effort(...)` remains in use for non-log effects such as
  trace recording, job enqueue, configuration decoding, and callback capture.
- Failure event names and correlation fields are preserved; the shared writer
  now consistently adds the source `audit_event` to diagnostic metadata.
- An AST architecture test rejects direct domain reconstruction via
  `run_observed_best_effort(lambda: write_log_event(...))`.
- Focused observability and affected-domain regression tests: `453 passed`.
- `.venv/bin/pytest -q`: `1565 passed` with no warnings.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `78a8e74`.

## Next Review Batch

Audit remaining domain-owned broad exception boundaries after auxiliary log
projection is structurally unified.
