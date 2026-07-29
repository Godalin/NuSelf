# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Make daemon worker health distinguish graceful shutdown from silent premature
target exit. Every long-lived worker that returns before shutdown must produce
the same authoritative failure health and lifecycle observation as an
escaping target exception.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory worker lifecycle, iteration, health, and recovery contracts.
2. Compare escaping target exceptions with normal target return.
3. Reproduce a long-lived target returning before shutdown without failure
   health or `worker.failed`.
4. Specify graceful versus unexpected target completion.
5. Record typed unexpected exit through the shared worker failure path.
6. Ensure pushes and pull requests for ordinary `dev/**` branches run CI.
7. Run focused and full quality gates, commit by functional boundary, and push.

## Out Of Scope

- No automatic thread restart; `OwnedWorker` remains one-shot.
- No change to per-iteration retry timing.
- No change to worker health wire schema or lifecycle event schema.
- No failure for target return after the shared shutdown event is set.
- No change to synchronous dependency initialization failures before start.
- No expansion of release publication; the CI addition only validates
  development branches.

## Completion Evidence

- Escaping target exceptions already update health and publish
  `worker.started`, `worker.failed`, then `worker.stopped`.
- A target that returns while shutdown is not requested now records
  `DaemonWorkerUnexpectedExitError` through the shared target-failure path.
- Its health reports `alive=false`, the compact unexpected-exit error, and one
  consecutive failure; lifecycle order is `started`, `failed`, `stopped`.
- All production worker targets are long-lived until the shared shutdown event;
  premature return is therefore a lifecycle failure.
- A target that sets the shared shutdown event before returning remains a
  graceful stop with no error or failure count.
- Focused worker, daemon server, health payload, and operations audit tests:
  57 passed.
- Full suite: 2162 passed.
- Pyright: 0 errors, 0 warnings.
- `git diff --check` passed.
- Before this change CI triggered only for `main`, so direct pushes and pull
  requests targeting `dev/v0.3.x` received no GitHub Actions validation.
- Development policy and CI now include both pushes and pull requests for the
  complete `dev/**` branch family.
- CI workflow YAML parsing and `git diff --check` passed.

## Publication

Development-branch CI was implemented in `b5e8f4c`; premature worker-exit
health was implemented in `5a9f3d0`. Milestone publication is pending this
goal update and push.

## Next Review Batch

After this boundary is complete, review whether worker health needs explicit
staleness/readiness semantics beyond liveness and consecutive failures.
