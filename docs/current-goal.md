# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make auxiliary audit validation and persistence operate on one immutable
envelope. Producer contract errors must propagate before the best-effort
boundary, while persistence failure must report degradation without rebuilding
or retrying the original record.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory auxiliary audit construction, persistence, diagnostics, and
   caller-visible exception classification.
2. Correct the active-goal function name from generic
   `run_observed_best_effort(...)` to `write_observed_log_event(...)`.
3. Specify one-envelope validation/persistence ownership before code.
4. Persist the already-created envelope through `write_audit_envelope(...)`.
5. Prove exact envelope identity, frozen metadata/context, schema propagation,
   and no retry after uncertain/persisted failure.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No retry of the original auxiliary audit.
- No suppression of producer identity, payload, or JSON schema errors.
- No change to persistence-outcome classification or failure diagnostic schema.
- No change to generic non-log `run_observed_best_effort(...)`.

## Completion Evidence

- The duplicated path is `write_observed_log_event(...)`;
  `run_observed_best_effort(...)` does not construct audit envelopes.
- `write_observed_log_event(...)` currently creates one envelope outside its
  catch solely for validation, discards it, and calls `write_log_event(...)`,
  which captures a second message ID, timestamp, context, and payload.
- Contract errors from the first construction already propagate correctly.
- Persistence failures from the second construction are degraded and never
  retry the record, including close failure after a durable append.
- `write_observed_log_event(...)` now creates one envelope before its
  persistence boundary and passes that exact instance to
  `write_audit_envelope(...)`.
- Tests prove one construction, object identity at persistence, stable message
  ID and request context, frozen metadata despite caller mutation, producer
  schema propagation, and no retry after a persisted close failure.
- Audit-store failure tests now inject envelope persistence and diagnostic
  persistence independently instead of relying on the removed shared
  `write_log_event(...)` seam.
- Focused observability and best-effort tests: 37 passed.
- Full suite: 2127 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed.

## Publication

Single-envelope auxiliary audit persistence was implemented in `7254128`;
milestone publication is pending this goal update and push.

## Next Review Batch

Review direct diagnostic audit construction next. Failure reporting still uses
the broad `write_log_event(...)` convenience path, so verify whether diagnostic
validation and persistence need the same explicit immutable-envelope ownership
or whether its authoritative failure semantics require a different boundary.
