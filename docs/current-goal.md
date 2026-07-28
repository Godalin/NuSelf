# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. REPL exit cleanup executes transcript auto-save and memory curation
exactly once each while retaining the main-loop failure and every named cleanup
failure without one replacing another.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- EOF, command exit, normal return, and main-loop failure converge on one
  interactive exit boundary; EOF no longer invokes auto-save inline.
- `transcript.auto_save` and `memory.curator.run` execute exactly once and in
  order, including when auto-save fails.
- `InteractiveLifecycleError` retains every named cleanup failure and the
  original failure objects.
- A main-loop `SystemExit` is the lifecycle error's explicit cause when cleanup
  also fails; with successful cleanup the same control object and traceback
  are re-raised.
- `chat/interactive_cleanup_failed` records ordered steps and primary presence;
  diagnostic storage failure cannot replace the lifecycle error.
- Transcript rendering/export semantics and expected curator `RuntimeError`
  handling remain unchanged.
- Focused REPL lifecycle, CLI, activity, and session-state tests: 325 passed.
- Final full tests: 1370 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
REPL exit cleanup preserves primary and cleanup failure provenance.
