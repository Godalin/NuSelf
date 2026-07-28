# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Idle. The shared free-text agent and persona tool migration is complete.

## Active Branch

`dev/v0.3.x`

## Ordered Work

None until the next review batch begins.

## Out Of Scope

None while idle.

## Completion Evidence

- `TextAgent` accepts LangChain messages and requires a stripped, non-empty
  natural-language result without a fake structured schema.
- Text and structured agents use one shared endpoint invocation/failover
  primitive.
- Global and thread-scoped persona tool builders inject the capability once;
  handlers no longer construct an LLM.
- Both persona `default_llm().complete()` paths and hidden local fallback are
  removed.
- `.venv/bin/pytest -q`: `1465 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `e164674`.

## Next Review Batch

Audit the next remaining direct model boundary after persona tools.
