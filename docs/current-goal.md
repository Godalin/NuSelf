# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make observed runtime-event publication degrade subscriber delivery failures
without hiding producer contract errors or losing event identity.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit publisher construction, subscription, publication, and log sinks.
2. Separate producer contract failures from subscriber delivery failures.
3. Return the created envelope after partial delivery failure.
4. Preserve best-effort structured diagnostics for subscriber failures.
5. Verify invalid definitions and payloads propagate without false diagnostics.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep synchronous ordered subscriber delivery.
- Preserve independent delivery to later subscribers after one fails.
- Do not make lifecycle event projection authoritative over domain work.

## Completion Evidence

- `publish_observed_event()` catches only `EventDeliveryError`; unknown
  definitions, producer mismatches, and invalid payloads propagate.
- Partial subscriber delivery failure still reports a structured degraded
  diagnostic and returns the `RuntimeEnvelope` retained by the delivery error.
- The return contract is now always `RuntimeEnvelope`, so callers cannot
  misinterpret partial delivery as an event that was never created.
- Tests cover partial delivery identity, unknown producer propagation, invalid
  payload propagation, and absence of false delivery diagnostics.
- Focused runtime-event, observability, daemon-worker, and chat tests:
  `89 passed`.
- `.venv/bin/pytest -q`: `1503 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `83ba87d`.

## Next Review Batch

Audit event/log payload schema duplication and projection validation.
