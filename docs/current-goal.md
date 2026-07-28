# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Remove reason prompt generation's redundant endpoint preflight so the shared
structured agent is the single model-availability boundary.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Specify that prompt generation does not construct models for preflight.
2. Remove direct `configured_langchain_chat_models` use.
3. Let `default_structured_agent` construct endpoints exactly once.
4. Preserve `ReasonPromptError` and the original shared runtime cause.
5. Verify injected agents bypass configuration and no-model failure is typed.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep the explicit project-root requirement.
- Keep exact `ReasonPromptOutput` validation in the shared structured agent.

## Completion Evidence

- `reason.prompt` no longer imports or calls
  `configured_langchain_chat_models`.
- The default structured agent constructs configured endpoints once and the
  shared endpoint runner owns no-model detection.
- No-model generation raises `ReasonPromptError` with
  `RuntimeError("no configured LangChain model")` preserved as its cause.
- Injected structured agents continue to bypass model configuration.
- Exact `ReasonPromptOutput` validation remains unchanged.
- `.venv/bin/pytest -q`: `1464 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `825dffe`.

## Next Review Batch

Audit composition roots that still construct configured endpoints directly
instead of receiving an agent capability.
