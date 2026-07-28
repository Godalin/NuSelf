# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. Chat now has one framework-native typed response protocol plus one
strictly plain-text deterministic local fallback.

## Active Branch

`dev/v0.3.x`

## Ordered Work

No active implementation work.

## Out Of Scope

Start the next review batch by replacing this idle objective before changing
code.

## Completion Evidence

- LangChain agent state must contain `structured_response`; message content is
  never reparsed.
- The no-model fallback wraps plain text with default structured metadata and
  rejects response-shaped JSON, fenced JSON, and visible tool-call markers.
- Prompted/fenced chat JSON parsers, the generic LLM JSON helper, and obsolete
  runtime parser methods are deleted.
- `ConversationResponseService` is the typed injection boundary for tests and
  alternate composition roots.
- Conversation evaluation fixtures store a structured `response` object and
  inject it directly; the old `llm_response` string field is removed.
- Focused chat, daemon, synthesis, response, and evaluation tests: 116 passed.
- Final full tests: 1377 passed.
- Pyright: 0 errors.
- `git diff --check`: passed.

## Publication

All local commits remain pending until explicit push authorization.

## Next Review Batch

Audit compatibility callbacks in CLI composition and then explicit legacy
persisted-data fallbacks, removing only those without a current migration
contract.
