# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make recoverable memory-curator auto-accept failures observable while retaining
the durable pending candidate and preventing unsafe suppression of storage bugs.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Trace candidate persistence, accept, cursor, and partial-failure order.
2. [x] Specify recoverable versus authoritative auto-accept failures.
3. [x] Add declared exception filtering to shared best-effort observability.
4. [x] Report validation/not-found auto-accept failures and retain pending state.
5. [x] Keep unexpected storage/programming failures propagating.
6. [x] Run focused/full tests, type checking, and formatting checks.
7. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Making candidate and target persistence one cross-repository transaction.
- Retrying failed auto-accept in the same curator run.
- Changing candidate validation, review-state, or manual review behavior.
- Swallowing SQLite, filesystem, or unexpected implementation failures.

## Completion Evidence

- Descriptor validation/not-found failures leave the candidate pending, emit a
  structured degraded event with candidate identity, and allow cursor advance.
- The next curator pass does not recreate the same pending candidate.
- Undeclared exceptions from accept still propagate and prevent cursor advance.
- Shared best-effort callers retain their existing catch-all default.
- Focused auto-accept tests, full pytest, Pyright, and `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit legacy persona name-index recovery and remaining legacy-file corruption
boundaries.
