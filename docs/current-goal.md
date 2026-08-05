# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — implementation complete; finalizing commits.

## Objective

Make every agent Tool builder consume resolved services/providers and one
caller-owned `FeatureExecutor`, then materialize string-returning decorated
functions through the single LangChain adapter.

## Next Steps

1. Completed: `ToolResources` now holds services/providers, and central Chat
   composition materializes Persona Tools.
2. Completed: every domain Tool builder requires explicit executor injection.
3. Completed: Reason shares one executor across workspace and Persona Tools.
4. Completed: the string-returning materialization contract and architecture
   guards are executable.
5. In progress: commit the verified change, then return this file to Idle.

## Exclusions

- Do not change which Tool operations require confirmation without a separate
  product-policy decision.
- Do not decorate domain Service methods directly or move Agent rendering into
  services.
- Do not introduce a Tool registry, Tool base class, or parallel LangChain
  execution protocol.

## Completion Evidence

- No domain Tool builder constructs its own `FeatureExecutor`.
- `ToolResources` contains no pre-materialized `BaseTool` collection.
- Chat and Reason each inject one executor into all tools they construct.
- `materialize_tool()` accepts only string-returning feature callables.
- Architecture tests pass as part of 2,333 passing unit tests.
- `uv run --locked pyright` reports zero errors and warnings.
- `git diff --check` passes.
