# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Active — make Source query state immutable after import.

## Objective

Separate read-only Source queries from append-only ingestion so imported
document revisions are never replaced or deleted through the Source API.

## Next Steps

1. Specify immutable revisions and the query/import capability split.
2. Make repository insertion transactional and idempotent by revision identity.
3. Remove delete/replace APIs and migrate CLI composition and tests.
4. Run full validation and publish a focused PR to `dev/v0.4.x`.

## Exclusions

- Do not mutate existing persisted Source records during migration.
- Do not add Source write tools to Chat.
- Do not fold Source into personal Memory.

## Completion Evidence

- `SourceService` exposes query operations only.
- Reimporting unchanged content is idempotent; changed content creates a new
  immutable revision atomically with all chunks.
- No Source delete or replacement API remains.
- Full pytest, Pyright, build, wheel smoke, and diff checks pass.
