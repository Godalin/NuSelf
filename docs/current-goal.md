# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle — no active implementation goal.

## Last Completed Goal

Simplified daemon and application-service composition without changing
storage, configuration, wire protocol, or user-visible behavior.

## Completion Evidence

- Removed repository-only forwarding factories and two empty composition
  modules; the application root now constructs simple repositories directly.
- `ApplicationGraph` no longer stores or exposes the raw backend. Reflection
  receives only its scheduler-state collection.
- Daemon health reads the scheduler directly, memory admission is private, and
  the typed task kind is the only runtime catalog source.
- Focused daemon/API boundary suite: 91 passed.
- `uv run --locked pytest -q`: 2450 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- `uv build`: `nuself-0.3.1` sdist and wheel built successfully.
