# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Prove and finish the shared runtime infrastructure migration. Every applicable
handler, log/audit projection, internal event, durable job wake-up, and
result-producing thread boundary must use the authoritative shared primitive
without parallel protocols or bypass paths.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Derive a concrete checklist from development, runtime, log, and error specs.
2. Inventory all dispatch maps, event callbacks, definition lookups, queues,
   one-shot threads, log writes, and caught-exception presentation.
3. Classify each occurrence as shared infrastructure, intentional domain
   policy, or an unsupported parallel/bypass path.
4. Specify and implement every required migration or contract correction.
5. Add requirement-level tests for each repaired boundary.
6. Run focused and full quality gates, commit by functional boundary, push,
   and confirm final development-branch CI.

## Out Of Scope

- No new user feature or agent capability.
- No cosmetic module movement without a demonstrated infrastructure boundary.
- No replacement of domain retry, scheduling, or persistence policy with a
  generic mechanism.
- No compatibility aliases or dual protocols after an in-repository migration.
- No claim of completion from tests alone without source inventory evidence.

## Completion Evidence

- Shared primitives and their governing contracts already exist in
  `runtime.handlers`, `runtime.events`, `runtime.definitions`, `runtime.jobs`,
  `runtime.execution`, `runtime.observability`, and `runtime.diagnostics`.
- Handler inventory: daemon requests, argparse commands, and canonical REPL
  commands each use a composition-owned sealed `HandlerRegistry`; no other
  callable dispatch map remains. Daemon and REPL prove closed-catalog coverage.
- Event inventory: the only production projection attachments bind the
  bounded synchronous runtime log sink. `ActivityBroker` remains the explicit
  bounded cross-process subscription transport rather than masquerading as an
  `EventPublisher` projection.
- Definition inventory: every domain audit, runtime event, job, warning, and
  observability definition registry is sealed by its builder before runtime
  resolution.
- Job inventory: only `JobDefinitionRegistry` constructs `JobMessage`, and the
  reason-export worker is the only durable job wake-up owner; it uses
  `JobAdmissionQueue`.
- Execution inventory: production `threading.Thread` construction exists only
  in shared `OwnedWorker` and `OwnedCall`; delayed timers exist only in
  `DelayedTaskScheduler`.
- Log inventory: direct `write_log_event` calls remain only inside the log and
  observability cores plus authoritative notification/tool projections.
  Auxiliary domain audits use `write_observed_log_event` or the shared
  observed-operation boundary.
- Exception inventory found four presentation bypasses: interactive
  `OwnedCall` errors, event-delivery aggregation, SQLite rollback wrapping, and
  JSON decode wrapping. All now use the shared sanitized diagnostic formatter
  while retaining the original exception objects and causes.
- Existing AST guard proves caught exceptions are not directly formatted.
  New sensitive-value tests cover the thread-result, aggregate, cleanup, and
  protocol-wrapper paths that direct `except` syntax scanning cannot see.
- Focused error-boundary and architecture-guard tests: 191 passed.
- Full suite: 2195 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check`, sdist/wheel build, and clean-wheel CLI/runtime import
  smoke passed.

## Publication

Curator locking is published in `7405167`. Infrastructure audit and local
validation are complete; functional commit, final publication, and final-push
CI remain.

## Next Review Batch

After this audit is proven complete, return the board to idle before discussing
new feature development.
