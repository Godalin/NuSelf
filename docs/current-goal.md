# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Prevent sidecar unlock or close failures from replacing the authoritative log
append outcome or its primary exception.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit lock acquire, body, unlock, and close exception precedence.
2. Specify authoritative acquisition and secondary cleanup behavior.
3. Encapsulate the sidecar handle lifecycle in one context manager.
4. Emit safe non-raising cleanup diagnostics.
5. Verify successful and failed appends under unlock failure.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Sidecar open and exclusive-lock acquisition failures still prevent append.
- Unlock and sidecar-handle close failures remain secondary because they occur
  after the authoritative append outcome is known.
- Cleanup diagnostics exclude event content, paths, and exception messages.

## Completion Evidence

- One `_locked_log_sidecar(...)` context now owns sidecar open, exclusive
  acquisition, unlock, and close ordering.
- Open/acquire errors prevent append and observer delivery; cleanup errors are
  reported only after the append result is authoritative.
- An unlock failure after success preserves the returned event and observer
  delivery; the same failure after an append error preserves that original
  append exception.
- Unlock and close diagnostics expose only component, operation, and exception
  type, excluding private paths and exception messages.
- Focused log infrastructure tests: `57 passed`.
- `.venv/bin/pytest -q`: `1553 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `343be8b`.

## Next Review Batch

Audit active-log handle close failures and durability escalation policy.
