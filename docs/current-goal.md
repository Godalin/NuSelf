# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Unify secondary observability failure diagnostics so audit writes and internal
event delivery cannot invent ad hoc failure names, messages, or metadata.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory every `failure_event`, failure message, metadata shape, owner,
   renderer, and test expectation.
2. Separate audit-sink projection failures from runtime event-delivery
   failures and preserve the original primary operation boundary.
3. Update observability, log, runtime-infrastructure, and development specs
   before implementation.
4. Define one closed diagnostic taxonomy with fixed projection defaults and
   exact metadata variants.
5. Migrate domain audit adapters, request/worker/chat delivery, and tool
   outcome projection through the shared contracts.
6. Remove subsystem-specific write-failure aliases, free-form messages, and
   duplicate exception details.
7. Run focused and full quality gates, commit by functional boundary, and
   push.

## Out Of Scope

- No change to primary domain event identities or payloads.
- No swallowing of schema/programming errors before the best-effort boundary.
- No process-global registry combining primary domain audit definitions.
- No change to subscriber invocation or audit persistence semantics.

## Completion Evidence

- Approval audit ownership completed in `fe3b2f1`.
- `approval_prompted` and `approval_decided` now use one sealed registry with
  fixed messages/statuses and exact metadata.
- Affirmative, explicit decline, and EOF safe decline are durably
  distinguished; decisions are observed before execution or return.
- The stale `service_tool_approved` identity and raw decorator-local event
  builder were removed.
- Initial next-batch inventory finds 13 explicit failure-event names across
  domain audit writes, request rejection, tool projection, and internal event
  delivery.
- Focused tests: 340 passed; final approval contract tests: 19 passed.
- Full suite: 2020 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Approval audit ownership was implemented in `fe3b2f1`; milestone publication
is pending this goal update and push.

## Next Review Batch

Continue shared handler/log/message infrastructure review after observability
failure diagnostics are verified and published.
