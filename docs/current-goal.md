# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Unify `service_tool_called` ownership so Chat, Reason, approval decorators, and
persisted step snapshots use one exact tool-outcome contract.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory every live and persisted `service_tool_called` producer,
   metadata shape, renderer, and failure adapter.
2. Determine whether approval decorators duplicate middleware-owned outcome
   events and separate approval intent from completed tool execution.
3. Update the governing development, Reason, and CLI/log specs before
   implementation.
4. Define one shared tool-outcome adapter with exact component, status, error,
   service, tool, args, and result contracts.
5. Migrate Chat and Reason projections plus step-local snapshots through the
   same validated shape.
6. Remove obsolete decorator events, duplicate projections, raw metadata
   builders, and compatibility aliases.
7. Run focused and full quality gates, commit by functional boundary, and
   push.

## Out Of Scope

- No process-global registry containing every domain's audit events.
- No change to tool execution, approval decisions, middleware capture, or
  user-visible renderer layout unless current duplicate events require it.
- Persisted Reason step snapshots remain self-contained.
- One-shot CLI handler ownership was completed in `55cba4f`.
- Generic corrupt-record and audit-projection diagnostics remain shared.
- Generic corrupt-record diagnostics remain owned by observability.
- Generic audit-projection failure events remain owned by observability.

## Completion Evidence

- Initial inspection finds three producer paths: Chat middleware outcomes,
  Reason middleware outcomes, and the older `audit_log` decorator used around
  approval-gated tools.
- Chat and Reason use the rich `tool_log_metadata` shape, while `audit_log`
  emits a second pre-call record with only a tool name.
- Pending full inventory, design, implementation, and verification.

## Publication

One-shot CLI handler ownership was implemented in `55cba4f`; publication is
pending the milestone commit and push.

## Next Review Batch

Continue shared handler/log/message infrastructure review after tool outcome
ownership is verified and published.
