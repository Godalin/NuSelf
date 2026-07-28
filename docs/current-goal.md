# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Daemon instance locking preserves ownership failure provenance when
flock/unlock and file-handle close fail together during acquire or release.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Normal contention still raises `DaemonInstanceLockContended`, closes the
  contender handle, and leaves the owner resources untouched.
- A single system flock, unlock, or close failure retains its existing
  exception; acquire/release marks `acquired` false only when ownership was not
  obtained or was relinquished by the Python owner.
- Simultaneous flock/unlock and close failures raise
  `DaemonInstanceLockCleanupError` with operation, primary error, cleanup
  error, and the primary lock failure as explicit cause.
- Acquire cleanup also runs for `BaseException` lock failures, preventing a
  process interruption from skipping handle close.
- Contention exit/status/log behavior, cleanup order, and retry behavior are
  unchanged.
- Focused instance-lock, signal, and daemon-server tests: 43 passed.
- Final full tests: 1305 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
daemon instance locking preserves acquire/release dual failure provenance.
