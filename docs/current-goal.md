# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The chat compression text-agent migration is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

None until the next review batch begins.

## Out Of Scope

None while idle.

## Completion Evidence

- `ConversationStateManager` accepts an optional `TextAgent` and uses
  LangChain system and human messages for model-backed compression.
- `ChatLLM` and `ChatMessage` are removed from the compression collaborator.
- Runtime composition reuses configured LangChain endpoints through
  `LangChainTextAgent`.
- Missing, failed, or empty model output uses the bounded deterministic local
  summary and cannot block conversation persistence.
- `.venv/bin/pytest -q`: `1473 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `75b32d2`.

## Next Review Batch

Audit chat response and reason advancer agent orchestration after compression.
