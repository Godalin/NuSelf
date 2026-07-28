# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close Reason's audit ownership so scheduler, advancer, service, and agent-tool
callers use one sealed domain registry instead of authoring raw projections.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory Reason events and payloads across the former output-only
   registry, scheduler, advancer, service, and the agent tool.
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

- Inventory found 24 output/export events already closed in an output-only
  registry and 12 lifecycle, proposal, trace, scheduler, and advancer events
  still authored as parallel string protocols.
- `service_tool_called` remains the intentional shared tool-event contract and
  is not duplicated into the Reason registry.
- `docs/spec/reason.md` and `docs/spec/reason-output.md` now define the unified
  registry, fixed messages, exact metadata, and privacy boundary before code
  migration.
- `nuself.reason.audit` now owns all 36 Reason lifecycle, peripheral, output,
  and export-worker event definitions; the output-only module and names were
  removed without compatibility aliases.
- All Reason producers use domain adapters except the intentionally shared
  `service_tool_called` projection.
- Focused Reason/Output/export-worker/Chat suite: `228 passed`.
- Full test suite: `1988 passed`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- `git diff --check` passed.

## Publication

Pending this batch's implementation commit and push.

## Next Review Batch

Continue infrastructure review after Reason audit ownership is verified and
published.
