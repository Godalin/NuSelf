# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Close daemon process-log rotation terminal warning ownership so the final
domain warning producer uses a sealed typed contract.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory process-log rotation, startup continuation, safe fields,
   stacklevel, warning policy, and tests.
2. Keep raw daemon process-log retention distinct from structured log rotation.
3. Update log, error, runtime-infrastructure, and development specs first.
4. Define one sealed `daemon/process_log_rotation_failed` warning with exact
   exception-type metadata and a fixed startup-continuation suffix.
5. Route daemon startup through registered rendering without changing rotation,
   hardening, open, spawn, or readiness behavior.
6. Remove the final production domain `emit_runtime_warning` call and
   free-form interpolation without compatibility aliases.
7. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No change to retention thresholds, backup order, or rotation operations.
- No exception message, project path, or process-log content in the warning.
- No structured diagnostic write or startup retry.
- No change to daemon status validation, spawn, or readiness semantics.

## Completion Evidence

- Daemon process-log rotation warning ownership completed in `eb6f76d`.
- `DAEMON_LIFECYCLE_WARNING_REGISTRY` is sealed and owns the exact
  `daemon/process_log_rotation_failed` contract.
- Rotation failure warning retains only `error_type` plus the fixed
  `continuing startup` suffix and cannot expose its message or path.
- Full-tree search proves production domain code no longer calls
  `emit_runtime_warning` directly; only the primitive and registered renderer
  remain.
- Focused tests: 363 passed.
- Full suite: 2069 passed.
- Pyright: 0 errors, 0 warnings.
- Static search and `git diff --check`: passed.

## Publication

Daemon process-log rotation warning ownership was implemented in `eb6f76d`;
milestone publication is pending this goal update and push.

## Next Review Batch

Remove the CLI import-time global `warnings.warn` monkeypatch next. Warning
suppression must be scoped to the specific third-party import and must not
alter process-wide warning behavior after `nuself.cli` loads.
