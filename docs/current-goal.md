# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Daemon and REPL named cleanup execution shares runtime infrastructure so
every cleanup `BaseException` is retained consistently while domain lifecycle
errors keep ownership of diagnostics and propagation.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- `runtime.cleanup` owns public `CleanupFailure` and `run_cleanup_steps`.
- The shared runner attempts every named operation exactly once, preserves
  order, and retains the same `Exception`, `KeyboardInterrupt`, and
  `SystemExit` objects.
- Daemon and REPL both use the shared runner; their lifecycle error classes,
  diagnostic events, step composition, ordering, and primary-error policy
  remain domain-owned.
- Daemon lock-release `KeyboardInterrupt` is aggregated after a serve failure,
  with the serve failure retained as explicit cause.
- Existing daemon cleanup ordering, REPL exact-once exit cleanup, diagnostic
  fallback, and successful lifecycle behavior remain unchanged.
- Focused shared cleanup, daemon instance, and REPL lifecycle tests: 21 passed.
- Final full tests: 1372 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
daemon and REPL share one named cleanup runner.
