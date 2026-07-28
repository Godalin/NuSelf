# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. REPL daemon-activity open, poll, final-drain, and close degradation is
observable without allowing auxiliary live-log transport to alter the chat
result; turn-scoped fallback recovers events without replaying delivered ones.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Open, poll, final-drain, and close connection/application failures emit
  `chat/activity_transport_degraded` with stage, error kind, subscription id,
  and structured daemon-client context when available.
- Failure of the degradation diagnostic itself falls back to a runtime warning
  and cannot replace or retry a successful chat result.
- Open, poll, and final-drain degradation reads the existing turn-scoped
  incremental cursor; close failure remains diagnostic only.
- Subscription-delivered event identities are registered through
  `InteractiveLogCursor.mark_seen()` before presentation.
- Poll fallback recovers a later persisted event while presenting an earlier
  subscription-delivered event exactly once.
- Healthy daemon activity remains subscription-only; unexpected poll and
  renderer failures retain their authoritative propagation and cleanup.
- Focused REPL activity, log infrastructure, CLI, and CLI chat tests:
  336 passed.
- Final full tests: 1362 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Continue auditing broad exception catches and local best-effort wrappers after
REPL activity transport degradation is observable and recoverable.
