# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle.

## Objective

No active development objective.

## Completed Goal

The lean replaceable-frontend boundary is complete. Approval remains one small
injected port, while presentation activity publishes directly through the
existing typed `EventPublisher`. The duplicate `FrontendEvent`, sink, adapter,
and null audit sink were removed; no web framework, remote interaction
protocol, manager, registry, compatibility shim, or second event bus was added.

Final evidence:

- the implementation commit is a net deletion: 135 inserted and 218 deleted
  lines including tests and documentation;
- local `uv run --locked pytest -q`: 2486 passed;
- local Pyright: 0 errors, 0 warnings;
- sdist and wheel build succeeded;
- clean Python 3.12 wheel install/import/CLI smoke succeeded;
- GitHub Actions run `30623952709` passed Ubuntu/macOS × Python
  3.12/3.13/3.14, including Pyright, tests, build, and clean-wheel smoke.

## Next Goal

Define a new objective, ordered steps, exclusions, and completion evidence
before beginning the next non-trivial change.
