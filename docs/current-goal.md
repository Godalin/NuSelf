# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close Reason's audit ownership so scheduler, advancer, service, and agent-tool
callers use one sealed domain registry instead of authoring raw projections.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory Reason events and payloads across `output_audit`, scheduler,
   advancer, service, and the agent tool.
2. Separate stable audit metadata from private prompts, summaries, errors, and
   duplicated runtime correlation fields.
3. Expand or replace the existing output-only registry with one sealed
   Reason-owned taxonomy and fixed event messages.
4. Route every Reason producer through domain adapters; remove parallel raw
   observability calls and obsolete event aliases.
5. Preserve scheduling, advancement, workspace, trace, and tool behavior when
   auxiliary audit persistence fails.
6. Update the governing spec and changelog where user-visible log contracts
   change.
7. Run focused and full quality gates, commit by functional boundary, and
   push.

## Out Of Scope

- No process-global registry containing every domain's audit events.
- No change to Reason model decisions, scheduling policy, workspace content,
  trace content, or thread state transitions.
- No migration or rewriting of historical Reason JSONL records.
- Memory audit ownership was completed in `219df65`.
- Generic corrupt-record and audit-projection diagnostics remain shared.
- Generic corrupt-record diagnostics remain owned by observability.
- Generic audit-projection failure events remain owned by observability.

## Completion Evidence

- Pending Reason inventory, design, implementation, and verification.

## Publication

Memory peripheral audit ownership was implemented in `219df65`; publication is
pending the milestone commit and push.

## Next Review Batch

Continue infrastructure review after Reason audit ownership is verified and
published.
