# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. One framework-native structured-agent invocation boundary now owns typed
output and failover, and manual memory intake no longer reparses model text.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- Shared `LangChainStructuredAgent` builds no-tool agents through
  `create_agent(..., response_format=ToolStrategy(schema))`.
- The runner accepts only an actual requested schema instance from
  `structured_response`; missing state, dictionaries, and wrong models fail.
- Endpoint availability failures use the configured ordering and common
  endpoint-success state. Protocol failures do not trigger another protocol.
- Memory intake uses framework messages and the shared typed runner. Prompted
  JSON, fenced-text extraction, `model_validate_json`, and `llm=` injection
  are removed from this path.
- Focused structured-agent/intake/CLI tests: 22 passed.
- Final full tests: 1453 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

Push is authorized; completed review batches are published immediately after
their validated commit.

## Next Review Batch

Migrate memory curator and optimizer to the shared structured-agent boundary.
