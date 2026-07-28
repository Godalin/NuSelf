# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. REPL session-header presentation now follows one explicit lifecycle.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `SessionHeaderPresenter` owns session-header rendering through one injected
  status provider.
- REPL startup, dispatcher `redraw_header`, and every completed non-command
  turn call the same presenter exactly once.
- `InteractiveSession` no longer stores presentation-only last-header state,
  and the root no longer implements a parallel conditional renderer.
- A consecutive-turn regression test proves output contains exactly one startup
  header plus one header after each of two turns with unchanged thread/status.
- Focused presentation/session/dispatcher/turn/CLI tests: 308 passed.
- Final full tests: 1271 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Extract remaining REPL reply/banner presentation or resume cross-subsystem
infrastructure review.
