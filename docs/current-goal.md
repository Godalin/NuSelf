# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The shared atomic file boundary preserves both the authoritative
write/replace failure and temporary-file cleanup failure when both occur.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- A partial write failure propagates unchanged, preserves the prior
  destination, and removes its unique sibling temporary file.
- A replace failure with successful cleanup retains its existing exception and
  leaves no temporary artifact.
- Simultaneous replace and unlink failures raise `AtomicWriteCleanupError`,
  exposing `primary_error`, `cleanup_error`, and the residual temporary path,
  with the primary persistence error as the explicit cause.
- Successful text/JSON writes, validation, destination replacement,
  concurrency, and retry behavior are unchanged.
- Focused storage, daemon PID, and LLM state tests: 31 passed.
- Final full tests: 1298 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
the shared atomic writer preserves dual failure provenance.
