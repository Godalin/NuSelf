# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Model daemon ownership and readiness as one explicit lifecycle phase.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Audit every `DaemonStatus` constructor, consumer, and ownership check.
2. Replace stored `running` with explicit stopped/owned/ready phases.
3. Make ownership inspection failure a typed unknown snapshot.
4. Wrap status failure consistently in start/stop lifecycle errors.
5. Render phases and status-unavailable errors across CLI entrypoints.
6. Verify every phase, PID gating, error causes, and command exit behavior.
7. Run full quality gates, commit, and push.

## Out Of Scope

- Server readiness publication order remains unchanged.
- Worker health remains separate from process ownership/readiness phase.
- No compatibility alias preserves boolean constructor input.

## Completion Evidence

- `DaemonStatus.phase` is authoritative across `stopped`, `owned_unready`,
  `ready`, `inconsistent`, and typed-error `unknown`; `running` is derived.
- Status combines typed ping and non-blocking instance-lock ownership, and a
  missing lock returns stopped without creating runtime metadata.
- Only `ready` may carry PID identity; construction rejects PID on every other
  phase and observation reads PID only after ready is proven.
- `DaemonStatusError` retains an unknown partial snapshot and original lock
  failure; start/stop wrap it as typed lifecycle failures with full chaining.
- Initial start rejects an existing unready owner without spawning a competing
  child; inconsistent readiness fails rather than being treated as stopped.
- CLI status/list/system/entrypoint surfaces render phase directly, report
  ownership inspection failure safely, and return non-zero when unavailable.
- Chat/open one-shot fallback is permitted only for `stopped`; owned-unready or
  inconsistent state cannot start concurrent local work.
- Direct tests cover all phase combinations, PID gating, no-write stopped
  observation, status-error causality, start rejection, CLI errors, and fallback
  prevention.
- Focused lifecycle and CLI suites: `359 passed`.
- Full test suite: `1722 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through implementation commit `e032535`.

## Next Review Batch

Review daemon status observation cost and snapshot reuse after phase modeling is
authoritative.
