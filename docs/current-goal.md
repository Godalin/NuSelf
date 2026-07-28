# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The reason prompt structured-agent migration is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

None until the next review batch begins.

## Out Of Scope

None while idle.

## Completion Evidence

- `ReasonPromptOutput` is strict, extra-forbid, and requires a non-blank
  generated prompt.
- Prompt generation uses LangChain messages through the shared
  `StructuredAgent` runner and consumes only the typed output.
- Direct `default_llm().complete()`, raw response trimming, and the parallel
  text-model protocol are removed from reason prompt generation.
- Failure still raises `ReasonPromptError` before any thread is persisted.
- `.venv/bin/pytest -q`: `1460 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `62081ca`.

## Next Review Batch

Design a shared free-text agent capability, then migrate both global and
thread-scoped `persona_think` without weakening its natural-language contract.
