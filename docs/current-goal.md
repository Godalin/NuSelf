# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make daemon lifecycle transitions explicit and audit their actual outcomes.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit start/stop return values, restart orchestration, and completion audits.
2. Define typed start, stop, and restart transition results.
3. Distinguish changed transitions from already-ready/stopped idempotent calls.
4. Centralize restart orchestration for one-shot and interactive callers.
5. Project outcome and before/after phases in every completion audit.
6. Reuse the stop result as restart's initial start snapshot.
7. Run full quality gates, commit, and push.

## Out Of Scope

- Status phase semantics and server readiness ordering remain unchanged.
- Failure exception types and safe terminal messages remain unchanged.
- Lifecycle audit persistence remains best-effort and non-authoritative.

## Completion Evidence

- `lifecycle.start()` and `stop()` now return invariant-checked typed results
  retaining the before/final snapshots and explicit idempotent outcomes.
- `changed` is derived from `started`/`stopped` rather than inferred from the
  final phase; `already_ready` and `already_stopped` remain successful no-ops.
- Result construction rejects invalid final phases, cross-runtime snapshots,
  and restart transitions whose start input is not the stop output.
- `cli/daemon_lifecycle.py` is the shared observable orchestration boundary for
  one-shot commands, the default launcher, and interactive restart.
- CLI and REPL no longer own separate restart algorithms. Both consume one
  `DaemonRestartResult` containing the authoritative stop and start results.
- Restart passes the stop result's final snapshot directly into start, avoiding
  a redundant observation between the ordered transition phases.
- Start/stop completion audits now record outcome, changed, and before/after
  phases. Restart emits one combined completion containing both transitions.
- Restart failure audits identify the failed `stop` or `start` stage while
  preserving the existing typed exception and safe terminal behavior.
- Common status formatting and lifecycle orchestration no longer live in the
  concrete daemon command-handler module.
- Direct tests cover result invariants, idempotent audit semantics, combined
  restart metadata, snapshot handoff, and failure-stage projection.
- Focused lifecycle and CLI suites: `368 passed`.
- Full test suite: `1731 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through implementation commit `b0b81ad`.

## Next Review Batch

Review lifecycle audit event/schema typing after orchestration is centralized.
