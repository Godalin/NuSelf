# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close shared agent endpoint failover audit ownership so Chat, Memory, Persona,
Reason, and Reflection use one exact safe contract without persisting endpoint
URLs.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory every shared endpoint runner caller, component, event consumer,
   retry/failover boundary, metadata, and redaction path. The inventory found
   five real caller components: Chat, Memory, Persona, Reason, and Reflection.
2. Separate per-endpoint failover observations from final aggregate
   capability failure and domain-specific retry events.
3. Update config, error, log, agent-tool, and development specs before
   implementation.
4. Define one sealed endpoint audit registry with fixed messages, statuses,
   exact safe metadata, and allowed caller components.
5. Route the shared endpoint runner through the adapter without changing
   retry/failover decisions or exception identity.
6. Remove `_report_endpoint_failure`, raw observability calls, endpoint URL
   metadata, and compatibility aliases.
7. Run focused and full quality gates, commit by functional boundary, and
   push.

## Out Of Scope

- No change to endpoint ordering or persisted successful-endpoint preference.
- No change to availability classification or attempts per endpoint.
- No change to domain-specific retry observers.
- No change to final raised aggregate failure.

## Completion Evidence

- Shared agent endpoint audit ownership completed in `28aaa14`.
- Chat, Memory, Persona, Reason, and the previously omitted Reflection caller
  now use one sealed registry containing ten exact component/event contracts.
- The shared runner retains retry/failover decisions and supplies only the
  already-decided outcome, non-negative endpoint index, and model.
- `_report_endpoint_failure` and endpoint base URL metadata were removed
  without compatibility aliases.
- Focused tests: 122 passed.
- Full suite: 2048 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Agent endpoint failover audit ownership was implemented in `28aaa14`; milestone
publication is pending this goal update and push.

## Next Review Batch

Close the remaining REPL Reason completion diagnostic that bypasses the sealed
Reason audit registry through a caller-selected `run_observed_best_effort`
event, then continue the shared handler/log/message infrastructure review.
