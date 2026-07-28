# Current Goal

NuSelf's short-lived execution board. Completed history belongs in Git and
`CHANGELOG.md`; deferred work belongs in [`TODOs.md`](TODOs.md).

## Objective

Move the shared prompt-message DTO out of `nuself.llm` so endpoint
infrastructure no longer owns agent-domain messages.

## Active Branch

`dev/v0.3.x`

## Ordered Work

1. Specify ownership for shared agent prompt messages.
2. Add `nuself.agent.messages` without coupling memory services to chat.
3. Migrate production and test imports from `nuself.llm`.
4. Remove dead message serialization and related endpoint-module types.
5. Verify `nuself.llm` contains endpoint infrastructure only.
6. Run full quality gates, commit, and push.

## Out Of Scope

- Keep the temporary `ChatMessage` DTO until callers migrate directly to
  framework message objects.
- Keep endpoint construction, preference persistence, redaction, and
  availability classification in `nuself.llm`.

## Completion Evidence

- `ChatMessage` now lives in `nuself.agent.messages`; chat, evaluation, and
  memory extraction import it from the shared agent domain.
- Memory does not depend on the chat subpackage.
- The unused `ChatMessage.to_wire()` method and its endpoint-module JSON types
  were removed.
- `nuself.llm` has no prompt-message declarations or imports.
- `.venv/bin/pytest -q`: `1466 passed`.
- `uvx pyright`: `0 errors, 0 warnings, 0 informations`.
- `git diff --check`: passed.

## Publication

`dev/v0.3.x` is published through `11643c7`.

## Next Review Batch

Audit the remaining custom prompt DTO and migrate compatible agent boundaries
to framework-native messages.
