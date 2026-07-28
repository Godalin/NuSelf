# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Delete the dead text-completion adapter stack from `nuself.llm` so the module
only owns framework model endpoints, endpoint preference, and shared error
classification.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Specify the remaining responsibilities of `nuself.llm`.
2. Remove `ChatLLM`, `LocalFallbackLLM`, and `default_llm`.
3. Remove the private text failover adapter and raw LangChain text invocation.
4. Delete adapter-only tests while retaining endpoint state and classification
   coverage.
5. Verify no production caller depends on the deleted protocol.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep `ChatMessage` as a temporary domain prompt DTO until its separate
  LangChain-message migration.
- Keep endpoint construction, preference persistence, redaction, and
  availability classification in `nuself.llm`.

## Completion Evidence

- Production code has no references to `ChatLLM`, `LocalFallbackLLM`,
  `default_llm`, `_LangChainFailoverLLM`, or `_invoke_langchain_model`.
- `nuself.llm` retains only endpoint construction, endpoint preference state,
  shared availability classification/redaction, and the temporary prompt DTO.
- Adapter-only tests were deleted while endpoint state coverage remains.
- `.venv/bin/pytest -q`: `1466 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `d4cace5`.

## Next Review Batch

Move the remaining `ChatMessage` DTO out of the endpoint infrastructure module.
