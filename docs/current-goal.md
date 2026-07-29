# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close approval audit ownership so prompt and decision events use one exact,
validated contract instead of decorator-local raw log calls.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory approval event producers, renderer consumers, component
   ownership, metadata, and failure diagnostics.
2. Decide the authoritative approval lifecycle and whether decline needs an
   explicit durable decision event.
3. Update agent-tool, CLI, log, and development specs before implementation.
4. Define a sealed approval audit contract with fixed messages, status/error
   policy, and exact per-event metadata.
5. Route the synchronous approval boundary through that contract without
   weakening prompt, input, callable, or diagnostic failure semantics.
6. Remove raw approval event builders, stale event names, and compatibility
   aliases.
7. Run focused and full quality gates, commit by functional boundary, and
   push.

## Out Of Scope

- No deferred approval or process-global pending callable registry.
- No change to which tools require approval.
- No change to middleware-owned completed tool outcomes.
- Generic audit-projection diagnostics remain owned by observability.

## Completion Evidence

- Tool outcome ownership completed in `e88a6c5`.
- Chat live logs, Reason live logs, and persisted Reason step snapshots now use
  one strict `ToolOutcomeProjection`.
- The obsolete pre-call `audit_log`, raw metadata builder, and redundant
  `service_tool_executed` approval event were removed.
- Approval decisions are now observed before the approved callable executes.
- Focused tests: 117 passed.
- Full suite: 2013 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Tool outcome ownership was implemented in `e88a6c5`; milestone publication is
pending this goal update and push.

## Next Review Batch

Continue shared handler/log/message infrastructure review after approval audit
ownership is verified and published.
