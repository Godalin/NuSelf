# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle — no active implementation goal.

## Objective

No active objective.

## Next Steps

1. Wait for the next explicitly approved goal.

## Exclusions

- Do not begin unapproved feature or refactor work.

## Last Verification

- Domain Tool builders accept services/providers and an explicitly injected
  `FeatureExecutor`; none silently creates its own execution environment.
- Chat and Reason share their caller-owned executor across all Tool builders,
  including Persona, Selves, and Workspace.
- `ToolResources` contains no materialized LangChain tools, and
  `materialize_tool()` accepts string-returning feature callables.
- `uv run --locked pytest`: 2,333 passed.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- `git diff --check`: passed.
