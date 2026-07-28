# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Finish Memory's peripheral audit ownership so Chat, daemon, and CLI callers no
longer author raw Memory/trace projections.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Inventory post-chat curator, daemon-triggered curator, manual Memory trace,
   and evidence-backed chat trace projections.
2. Expand the Memory registry from curation-only naming to the complete owned
   direct audit surface.
3. Register exact schemas for curator failure and chat-trace failure without
   duplicating private summaries or correlation ids.
4. Route Chat, daemon, CLI, and curator callers through Memory-owned adapters.
5. Remove the redundant `curator_changed` client projection; the curator's
   registered completion record remains authoritative for audit.
6. Preserve curator/trace results and user presentation when auxiliary
   projection persistence fails.
7. Run full quality gates, commit, and push.

## Out Of Scope

- No process-global registry containing every domain's audit events.
- No migration or rewriting of historical JSONL records.
- No change to curator decisions, cursor movement, Memory mutations, trace
  content, or post-chat scheduling.
- No migration of historical `curator_changed` or `trace_write_failed` logs.
- Reason trace/completion projections remain for the Reason audit batch.
- Generic corrupt-record and audit-projection diagnostics remain shared.
- Generic corrupt-record diagnostics remain owned by observability.
- Generic audit-projection failure events remain owned by observability.

## Completion Evidence

- The Memory registry now owns fourteen curation, optimizer, trace, and
  peripheral failure events with exact metadata and fixed failure messages.
- Chat, daemon, curator, and Memory CLI callers use Memory-owned adapters;
  `curator_changed` and its free-form summary projection were removed.
- Historical event migration remains intentionally out of scope.
- Focused Memory/Chat/daemon/CLI suite: `481 passed`.
- Full test suite: `1964 passed`.
- Pyright: `0 errors, 0 warnings, 0 informations`.
- `git diff --check` passed.

## Publication

Pending this batch's implementation commit and push.

## Next Review Batch

Select after this batch is verified and published.
