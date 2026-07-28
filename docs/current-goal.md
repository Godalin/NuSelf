# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Migrate Reason lifecycle/output/proposal audits to the shared observed log API
without weakening authoritative delivery or tool-middleware boundaries.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Classify reason, notification, and tool log effects by authority.
2. Preserve authoritative log-only delivery and middleware-owned callbacks.
3. Migrate reason scheduler, output, and proposal lifecycle audits.
4. Remove redundant reason-output lambda wrappers.
5. Verify committed/planned/composed results survive audit failure.
6. Run full quality gates, commit, and push.

## Out Of Scope

- `LogOnlyNotificationAdapter.send(...)` remains authoritative because its log
  write is the configured delivery effect.
- Tool runtime callbacks remain direct because shared middleware owns their
  failure reporter and primary-outcome isolation.
- Durable manifests, chunks, progress, queues, and Reason domain mutations
  continue to propagate failures.

## Completion Evidence

- Reason scheduler completion, output plan/enqueue/chunk/compose/PDF lifecycle,
  and proposal records now use `write_observed_log_event(...)`.
- A missing audit store cannot block an approved proposal from creating its
  thread or change a persisted scheduler step and cooldown.
- Full output planning/composition remains complete with manifests, progress,
  chunks, combined Markdown, and PDF when every lifecycle audit is unavailable.
- `LogOnlyNotificationAdapter` remains direct and authoritative; middleware
  tool-log callbacks remain direct with their existing shared failure reporter.
- Focused reason, export recovery, agent, and subagent tests: `122 passed`.
- `.venv/bin/pytest -q`: `1561 passed` with no warnings.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `d72f49f`.

## Next Review Batch

Audit middleware-owned tool-log callbacks and failure reporters for duplication.
