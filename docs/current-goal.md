# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Centralize framework tool service metadata interpretation so chat, skills, and
reason logging share one validated contract.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Specify one shared `service_component` interpretation rule.
2. Add shared single-tool and tool-index helpers.
3. Migrate chat call logging and skill grouping.
4. Migrate reason tool routing.
5. Verify valid, missing, and invalid metadata consistently.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Do not change renderer interpretation of persisted log-event metadata.
- Do not infer a service component from tool names.
- Do not require service metadata for tools that do not emit service-call logs.

## Completion Evidence

- `tool_service_component` is the sole framework-tool metadata interpreter and
  returns only string service components.
- `index_tool_service_components` builds validated name-to-service indexes and
  omits tools with missing or invalid metadata.
- Chat call logging, generated skill grouping, and reason tool routing use the
  shared helpers; production search finds no repeated direct interpretation in
  those runtimes.
- Unit tests cover valid, missing, numeric, and arbitrary-object metadata.
- `.venv/bin/pytest -q`: `1470 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `5f5ae9f`.

## Next Review Batch

Audit construction-time tool metadata assignment and remove the remaining
name-to-service mutation table.
