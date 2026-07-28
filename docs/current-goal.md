# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The ReasonAdvancer runtime-context unification batch is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- No reason-specific ContextVar remains.
- Workspace and persona tool providers resolve the active reason thread from
  RuntimeContext.
- Reason advance logs inherit the reason thread plus existing request, turn,
  job, trace, and source identity.
- Caller context is restored after successful and failed advances.
- Focused tests: 40 passed.
- Full tests: 1208 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit log-observer ContextVar ownership and propagation boundaries.
