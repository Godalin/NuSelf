# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Bound daemon raw process output without blocking daemon startup.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit ownership of the inherited daemon stdout/stderr descriptor.
2. Define the only safe rotation window before spawning a new daemon.
3. Add an injectable bounded size/backup policy for the raw stream.
4. Rotate owner-only backups before opening the next child descriptor.
5. Treat retention maintenance as secondary to daemon startup.
6. Verify ordering, backup bounds, permissions, warning safety, and handle close.
7. Run full quality gates, commit, and push.

## Out Of Scope

- A single long-running daemon may exceed the threshold; the next start
  restores the configured bound.
- The raw stream remains best-effort and is not parsed as structured JSONL.
- Structured component log retention and durability remain unchanged.

## Completion Evidence

- `DaemonProcessLogRetentionPolicy` owns a 5 MiB threshold and three backups,
  validates positive bounds, and remains injectable for tests.
- Rotation runs only after confirming no daemon is active and before the next
  child inherits the raw process-log descriptor.
- Active and numbered raw-stream files are hardened to `0600`; rotation keeps
  newest-first `.1` ordering and deletes the oldest bounded backup.
- The parent process closes its append handle immediately after spawn while the
  child retains the inherited descriptor.
- Rotation failure emits one warning containing only the exception type and
  continues daemon startup without exposing paths or exception text.
- The specification explicitly states that a single long-running daemon may
  exceed the threshold until its next start.
- Focused lifecycle and runtime-path suites: `21 passed`.
- Full test suite: `1672 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is ready to publish through implementation commit `ff1cafc`.

## Next Review Batch

Review daemon startup timeout and failure reporting after raw output retention
is bounded at the descriptor ownership boundary.
