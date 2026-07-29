# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Remove ad hoc per-turn thread ownership from interactive activity. One-shot
execution must atomically own start, result/exception handoff, and completion,
and no poll, presentation, or process-control path may abandon an in-flight
authoritative send.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory raw threads, join paths, start rollback, exception handoff, and
   cancellation claims.
2. Separate long-lived `OwnedWorker` lifecycle from one-shot result execution.
3. Specify a shared `OwnedCall` with exact start, completion, timeout, and
   exception-identity contracts.
4. Migrate live activity send and remove result/error/control side-channel
   lists.
5. Prove start rollback, single execution, timeout observation, exact exception
   transport, and cleanup after poll/presentation/control failures.
6. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No unsafe Python thread termination.
- No claim that a join timeout cancels model or daemon work.
- No agent/model cooperative cancellation protocol in this batch.
- No change to retry, activity rendering, or send-result policy.

## Completion Evidence

- Inventory found one raw production thread in live activity send.
- Normal completion and main-thread `KeyboardInterrupt` joined it, but
  unexpected polling or presentation failure could return while it remained
  alive.
- The control path waited only 0.5 seconds and then abandoned a still-running
  daemon thread; this was not real cancellation.
- Daemon requests have configured socket timeouts, while local one-shot model
  calls expose no shared cooperative cancellation contract.
- `runtime.execution.OwnedCall` now owns one non-daemon result-producing thread,
  duplicate-safe start, atomic start rollback, exact value/error outcome, and
  finite non-negative wait timeouts.
- The target transports the same escaping `BaseException` object and traceback;
  it does not convert process-control state into an ordinary failure.
- Live activity send uses `OwnedCall`; ad hoc result, error, and control lists
  plus its raw daemon thread were removed.
- Unexpected poll/presentation failures and main-thread control exceptions wait
  for the started send to finish before returning or re-raising. Start failure
  still closes an opened activity subscription.
- Static search finds thread construction only inside shared `OwnedWorker` and
  `OwnedCall` owners.
- Focused execution, REPL activity, and worker tests: 30 passed.
- Full suite: 2111 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed.

## Publication

Owned one-shot execution was implemented in `b347f10`; milestone publication
is pending this goal update and push.

## Next Review Batch

Review process-local log observation next. `observe_log_events(...)` is another
synchronous callback boundary used to feed daemon live activity. Verify that
its public semantics distinguish bounded in-process projection from arbitrary
observation, that nested scope restoration and failure diagnostics cannot
recurse, and that no slow or reentrant observer can unexpectedly acquire
authoritative log-write ownership.
