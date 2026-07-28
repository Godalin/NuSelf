# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Reason advancer, scheduler, and output-runner failure diagnostics cannot
mask the original exception or change scheduler cooldown/return behavior.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Advancer agent/tool failure writes structured `advance_tool_failed` without
  traceback payloads and propagates the exact original exception object.
- Scheduler applies and persists cooldown before best-effort
  `scheduler_advance_failed`; audit failure emits a terminal warning while
  `run_once()` returns `None` and persists no step.
- Output runner failure writes `reason_output_chunk_failed` best effort,
  propagates the exact runner exception, and writes no failed chunk.
- All three projections retain runtime/thread/job/chunk correlation and cannot
  introduce a hidden retry when structured logging fails.
- Successful events, prompts, step parsing, cooldown duration, and output
  retry behavior are unchanged.
- Focused advancer, scheduler, and output-runner tests: 23 passed.
- Final full tests: 1311 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
reason failure projections cannot replace their primary outcomes.
