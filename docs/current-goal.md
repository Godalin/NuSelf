# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — repairing daemon Chat approval and adding current-time access.

## Objective

Route approval-gated daemon Chat tools through a typed client challenge and
exact decision replay instead of treating a missing daemon frontend as user
rejection, and expose current local/UTC time through one read-only Tool.

## Next Steps

1. Specify the approval challenge, exact replay, and uncommitted-turn rules.
2. Implement daemon/client approval request and decision transport.
3. Distinguish genuine decline from unavailable approval infrastructure.
4. Add the `runtime_time` read-only Tool and runtime Skill guidance.
5. Verify protocol, approval, idempotency, time, and full-suite behavior;
   commit in stages and return this file to Idle.

## Exclusions

- Do not make the background daemon read terminal stdin.
- Do not execute an approval from activity/log events.
- Do not accept a decision for different Tool arguments or approval policy.
- Do not commit the first Chat attempt when it pauses for approval.

## Completion Evidence

- Daemon Chat returns a typed approval challenge when no decision is present.
- CLI/REPL prompts through `TerminalApprovalPort` and retries the same turn with
  a decision bound to the exact request.
- Approved and declined decisions reach the Tool; unavailable infrastructure
  is not reported as a user decline.
- Chat exposes `runtime_time` with local timezone and UTC timestamps.
- Full pytest, Pyright, and `git diff --check` pass.

## Progress

- Specified the typed daemon approval challenge and `runtime_time` contract.
- Implemented exact approval-grant replay without committing or reporting the
  paused first attempt as a failed turn.
- Added the read-only `runtime_time` Tool and runtime Skill guidance.
- Verified 2344 unit tests, Pyright, and `git diff --check` successfully.
