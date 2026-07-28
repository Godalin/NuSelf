# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Create one reason-advancer composition factory and migrate CLI, REPL, and
scheduler so model/workspace construction cannot drift.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Specify the shared reason-advancer composition contract.
2. Add a factory for workspace, configured endpoints, and optional tools.
3. Migrate CLI and REPL off inline construction.
4. Migrate scheduler while preserving explicit dependency injection.
5. Verify scheduler defaults load configured endpoints exactly once.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep `ReasonAdvancer` constructor injection-friendly for unit tests.
- Keep daemon endpoint/tool reuse through explicit scheduler arguments.

## Completion Evidence

- `default_reason_advancer` owns reason-scoped workspace and configured
  endpoint composition.
- CLI, REPL, and scheduler call the factory; none imports endpoint
  construction or assembles `ReasonAdvancer` inline.
- Default construction loads configured endpoints exactly once.
- An explicitly injected empty endpoint tuple remains empty and does not load
  project defaults.
- Scheduler still accepts explicit endpoints and readonly tools for daemon
  capability reuse.
- `.venv/bin/pytest -q`: `1466 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `fa9152b`.

## Next Review Batch

Replace daemon access to private chat runtime endpoint/tool attributes with an
explicit capability snapshot.
