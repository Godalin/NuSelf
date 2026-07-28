# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Eliminate mixed-protocol writers from structured component logs.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit every producer and reader of `private/logs/*.log`.
2. Reserve component log files exclusively for structured JSONL events.
3. Move daemon stdout/stderr to a distinct owner-only raw process stream.
4. Project optimizer activity through structured best-effort audit events.
5. Ensure logging failure cannot replace persisted optimizer candidates.
6. Verify paths, event schemas, parseability, and process-handle ownership.
7. Run full quality gates, commit, and push.

## Out Of Scope

- The daemon raw process stream is not parsed as structured JSONL and has its
  own best-effort append semantics.
- Existing malformed legacy component lines remain isolated by readers.
- Structured-log batching and throughput policy remains deferred until every
  producer obeys one protocol.

## Completion Evidence

- `RuntimePaths` now distinguishes structured `daemon_log_path` from raw
  `daemon_process_log_path`.
- Daemon stdout/stderr is appended only to owner-only
  `private/logs/daemon-process.log`; the parent closes its handle immediately
  after spawning, and structured readers never parse that stream.
- Memory optimizer deferred, candidate-staged, and completed activity uses
  canonical `LogEvent` JSONL through `write_observed_log_event(...)`.
- Optimizer audit metadata contains identifiers/actions/counts but excludes
  free-form candidate titles, bodies, reasons, and model failure text.
- Structured audit failure cannot replace a deferred result or already-saved
  optimizer candidate.
- A source-wide writer audit finds no remaining raw component-log append path.
- Focused optimizer, lifecycle, config, log, and CLI suites: `100 passed`.
- Full test suite: `1667 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is ready for publication through `324f1b3`.

## Next Review Batch

Review structured-log batching and throughput policy after all component-log
producers obey the structured event protocol.
