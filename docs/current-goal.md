# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Add golden conversation fixtures and a local evaluation command.

The conversation runtime now produces structured responses with evidence references, confidence, and epistemic status. The persona skeleton is gated, routed, and backed by durable memory instructions. The next step is to prevent regressions in fidelity and uncertainty behavior by adding reproducible evaluation fixtures and a CLI command that can run them without external services.

## Immediate Context

- `ChatResult` carries `answer`, `evidence_references`, `confidence`, and `epistemic_status`.
- `ConversationGraphRuntime` produces `ParsedChatResponse` via `_parse_chat_response`.
- `_apply_unsupported_claim_guard` flags personal claims without evidence.
- `MemoryQueryService.pack` returns ranked evidence with source metadata.
- The CLI already has a deep command tree (`daemon`, `chat`, `memory`, `thread`, `logs`).
- Tests use `FakeLLM` and `StructuredFakeLLM` to capture prompts and return stubbed JSON.

## Next Steps

1. Design a compact golden fixture format (e.g., YAML or JSON) that records a user message, expected answer patterns, required evidence references, expected epistemic status, and banned claim patterns.
2. Add a `nuself eval` CLI command that loads fixtures, runs them through `ChatAgent` with a fake or recorded LLM, and prints pass/fail per fixture.
3. Add scoring helpers for citation coverage, unsupported personal claims, uncertainty behavior, and style fidelity.
4. Keep fixtures under `tests/fixtures/conversations/` or `examples/fixtures/`.
5. Ensure the eval command can run offline with fake providers.
6. Update tests and documentation together with the implementation.

## Not Now

- Full multi-persona orchestration.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- At least one golden conversation fixture exists and is exercised in CI.
- A CLI eval command can run fixtures and report scores.
- Scoring covers citation coverage, unsupported personal claims, and uncertainty behavior.
- Eval runs offline with fake providers.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
