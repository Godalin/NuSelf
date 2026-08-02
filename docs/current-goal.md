# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Status

Idle — Memory/Source boundary and tool-driven context restoration complete.

## Objective

Keep Memory focused on chat-derived personal long-term memory. Extract imported
documents and future connectors into an independent Source domain. Remove
automatic Memory/Profile/Source retrieval from Chat context preparation; Skills
must guide the Agent to call Memory or Source tools only when needed.

## Next Steps

None.

## Exclusions

- Preserve persisted collection/wire schemas and existing user data.
- Preserve chat-derived Memory observation, curation, review, and optimizer
  behavior except where repository access is replaced by a service API.
- Do not automatically turn Source content into personal memory or profile.
- Do not add ambient RAG, compatibility import shims, package facades, or a
  generic event bus/connector framework before a second connector exists.

## Last Verification

- Source owns records, persistence, local ingestion, query service, agent
  tools, skill, and the top-level `nuself source` command family.
- Memory no longer imports Source/Profile in its query service; curator owners
  are grouped under `memory/curator/`.
- Chat and persona preparation perform no ambient Memory/Profile/Source
  retrieval. Conversation history and summaries remain intact; the Agent uses
  Memory/Source tools on demand.
- `uv run --locked pyright`: 0 errors, 0 warnings.
- Default `uv run pytest -q`: 2387 passed.
- `uv build`: sdist and wheel succeeded.
- Clean Python 3.14 wheel install/import smoke: passed.
