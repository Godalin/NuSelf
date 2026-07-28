# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Synchronous approval now keeps prompting, decisions, tool execution, and
structured results authoritative when secondary audit persistence fails.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- The approval decorator routes `approval_prompted`,
  `service_tool_executed`, and `service_tool_approved` through shared
  best-effort observability.
- Audit failure cannot skip a prompt, execute a declined tool, replace an
  approved result, or mask the original wrapped-tool exception.
- Each failure diagnostic identifies the failed approval operation and tool;
  diagnostic persistence failure emits `RuntimeWarning` without retry.
- Prompt text, JSON output, approval policy, decorator composition, and
  exactly-once tool execution are unchanged.
- Focused approval and best-effort tests: 13 passed.
- Final full tests: 1287 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
the approval boundary uses shared observability.
