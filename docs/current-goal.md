# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close shared agent endpoint failover audit ownership so Chat, Memory, Persona,
and Reason use one exact safe contract without persisting endpoint URLs.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory every shared endpoint runner caller, component, event consumer,
   retry/failover boundary, metadata, and redaction path.
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

- Storage cleanup audit ownership completed in `f643a8e`.
- Backend close and CLI cleanup failure now use one sealed storage operations
  registry.
- `runtime.cleanup` owns canonical ordered `{step,error}` projection shared by
  daemon and storage lifecycle owners.
- Storage/CLI no longer construct cleanup audit presentation.
- Initial next-batch inspection finds shared agent failover events for
  `llm_endpoint_failed_over` and `llm_endpoint_unavailable` emitted across
  Chat, Memory, Persona, and Reason; metadata currently includes `base_url`.
- Focused tests: 100 passed.
- Full suite: 2040 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Storage cleanup audit ownership was implemented in `f643a8e`; milestone
publication is pending this goal update and push.

## Next Review Batch

Continue shared handler/log/message infrastructure review after agent endpoint
failover audit ownership is verified and published.
