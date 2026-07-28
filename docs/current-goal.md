# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Delete the temporary `ChatMessage` protocol and use framework-native LangChain
messages across chat response, evaluation, and optional memory extraction.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Specify the framework-native prompt message contract.
2. Make `ConversationResponseService` consume LangChain `BaseMessage` values.
3. Build chat prompts directly as system, human, and AI messages.
4. Pass framework messages directly to optional LangMem extraction.
5. Delete `nuself.agent.messages` and migrate all tests.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep endpoint construction, preference persistence, redaction, and
  availability classification in `nuself.llm`.
- Keep persisted `ThreadMessage` as the chat storage wire model; it is not a
  model-invocation protocol.

## Completion Evidence

- `ConversationResponseService`, its LangChain supervisor, eval fixtures, and
  test doubles exchange `BaseMessage` values directly.
- `ConversationGraphRuntime` constructs `SystemMessage`, `HumanMessage`, and
  `AIMessage` prompts without an intermediate NuSelf DTO.
- Optional LangMem extraction receives the same framework-native messages
  directly.
- `nuself.agent.messages` and every production/test `ChatMessage` reference
  were removed.
- Endpoint-exhaustion logging names the deterministic local response policy,
  not a local LLM.
- `.venv/bin/pytest -q`: `1465 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `76b2feb`.

## Next Review Batch

Audit chat response orchestration for convergence with the shared structured
agent and endpoint failover infrastructure.
