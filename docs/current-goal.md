# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Keep structured event persistence available when bounded-retention rotation
encounters filesystem failures.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit rotation mutation order and write-failure boundaries.
2. Specify persistence-first degradation for retention failures.
3. Isolate rotation failures without weakening append failures.
4. Emit one safe non-raising rotation diagnostic.
5. Verify failures before and after active-file replacement.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Append, lock, and runtime-directory failures still propagate to the caller.
- Observers run only after the current event is successfully appended.
- Do not expose event content, filesystem paths, or exception messages in the
  degradation diagnostic.

## Completion Evidence

- Retention rotation `OSError`s are isolated from the active event append;
  lock, directory, and append failures remain outside the degradation boundary.
- A failed rotation before active-file replacement continues in the existing
  active file; a failure after replacement creates a new active file.
- Both recovery states preserve readable event history and deliver the
  successfully persisted event to process-local observers.
- Rotation diagnostics are non-raising and expose only component plus exception
  type, excluding event content, paths, and exception messages.
- Focused log infrastructure tests: `48 passed`.
- `.venv/bin/pytest -q`: `1544 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `762d32c`.

## Next Review Batch

Audit partial append recovery and record durability guarantees.
