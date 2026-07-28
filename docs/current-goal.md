# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Unify strict LangGraph `structured_response` decoding across shared structured
agents, chat, and reason without hiding their distinct tool middleware state.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Specify the shared strict structured-state decoder contract.
2. Extract the decoder into shared agent infrastructure.
3. Migrate `LangChainStructuredAgent`, chat, and reason.
4. Preserve chat's visible-tool-call rejection after typed decoding.
5. Verify wrong state, missing fields, dictionaries, and wrong schemas fail.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep `create_agent` composition local to each capability because chat and
  reason own distinct tools, prompts, and middleware state.
- Keep domain conversion and extra semantic validation after shared decoding.

## Completion Evidence

- `require_structured_response` is the sole production decoder for LangGraph
  `structured_response` state.
- `LangChainStructuredAgent`, chat response, and reason advance all use the
  shared decoder.
- The decoder rejects non-dictionary state, missing response state,
  dictionary-shaped payloads, and wrong schema instances without coercion.
- Chat runs visible tool-call rejection after the shared typed check.
- Reason projects captured tool outcomes before translating decoder failure to
  `ReasonAdvanceError`.
- Full-tree search finds no other manual structured-response extraction.
- `.venv/bin/pytest -q`: `1468 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `bd08835`.

## Next Review Batch

Audit remaining framework state parsing and model invocation outside shared
agent infrastructure.
