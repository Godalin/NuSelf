# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make the derived LLM endpoint preference state strictly validated, atomically
persisted, and observably recoverable when it is missing, stale, or corrupt.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. [x] Audit all readers and writers of `llm_state.json`.
2. [x] Specify a versioned derived endpoint-preference record.
3. [x] Reject booleans, negative indexes, partial records, and unsupported versions.
4. [x] Report corrupt state through the shared payload-safe diagnostic boundary,
   then fall back to configured endpoint order.
5. [x] Write successful endpoint state atomically and reject invalid writes.
6. [x] Avoid loading the same state twice while constructing `default_llm()`.
7. [x] Run focused/full tests, type checking, and formatting checks.
8. [x] Update user-facing docs/changelog and commit this stage.

## Out Of Scope

- Changing endpoint availability classification or request retry policy.
- Persisting endpoint failure counts, backoff, latency, or circuit-breaker state.
- Changing configured endpoint ordering or API-key filtering.
- Migrating other runtime state records in this same commit.

## Completion Evidence

- A valid saved endpoint remains first on the next process use.
- Missing state silently uses configured order because it is the normal first-run case.
- Malformed JSON, non-object state, booleans, negative indexes, partial records,
  and unsupported versions emit one payload-safe `record_decode_failed` event
  per load and use configured order.
- An index absent from the current filtered endpoint set is treated as stale,
  emits an observable diagnostic, and uses configured order.
- Successful writes use atomic replacement and include a schema version.
- `default_llm()` loads endpoint preference once during construction.
- Focused failover tests, full pytest, Pyright, and `git diff --check` pass.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing daemon lifecycle/runtime checkpoints and derived state for
strict validation, atomic recovery, and observable failure behavior.
