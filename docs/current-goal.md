# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Remove the legacy `ChatLLM` injection protocol from chat runtime/response and
make no-model behavior an explicit deterministic local response policy.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Specify local response versus framework agent behavior.
2. Remove `llm=` and `default_llm()` from chat runtime composition.
3. Replace endpoint exhaustion fallback with deterministic local response
   construction.
4. Migrate test doubles to `ConversationResponseService`.
5. Verify chat runtime owns only one real model protocol.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep `ChatMessage` prompt DTO until the separate LangChain-message migration.
- Remove now-dead legacy adapters from `llm.py` in the next commit.
- Preserve the visible no-model configuration guidance.

## Completion Evidence

- `ConversationGraphRuntime` and `ConversationResponseSynthesizer` no longer
  accept `llm=` or construct `default_llm()`.
- No-model, exhausted-endpoint, and post-tool retry-suppression paths construct
  deterministic typed local responses without invoking or parsing a fallback
  model.
- Generated chat test behavior now injects `ConversationResponseService`.
- `.venv/bin/pytest -q`: `1473 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `9f47913`.

## Next Review Batch

Delete dead `ChatLLM`, `default_llm`, and failover adapter code from
`nuself.llm`.
