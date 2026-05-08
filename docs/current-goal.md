# Current Goal

This file is the short-term execution guide for NuSelf. Keep it focused on the active target, immediate context, and the next few steps. Completed work belongs in the README TODOs, not here.

## Focus

Make the synthesizer the only user-facing voice.

The bounded persona skeleton now runs behind an activation gate, feeds synthesis into the response prompt, and stores persona instructions as durable memory. The current architecture injects the synthesizer's compact fusion into the main LLM's system prompt, and the main LLM still generates the final answer. The next step is to let the synthesizer directly produce the user-facing response, so the assistant voice is consistently the fused persona perspective rather than a separate main LLM acting on synthesis guidance.

## Immediate Context

- `PersonaGraphDriver` runs personas and a synthesizer step that produces `PersonaTurnState.synthesis`.
- `ConversationGraphRuntime.initial_response_node` calls `_build_prompt` and then `_llm.complete(prompt)`.
- The synthesis is injected into the system prompt as "Internal perspective fusion".
- `ChatResult` carries `answer`, `evidence_references`, `confidence`, and `epistemic_status`.
- `MinimalSynthesizerNode` currently fuses persona notes into a single summary string.
- `PersonaActivationPolicy` and persona definitions can now be loaded from durable memory.

## Next Steps

1. Extend `MinimalSynthesizerNode` (or add a new `SynthesizerResponseNode`) to produce a full `ParsedChatResponse` (answer, evidence_references, confidence, epistemic_status) instead of just a summary string.
2. When personas are activated, skip the main LLM initial_response node and use the synthesizer output directly as the final response.
3. When personas are not activated, keep the current single-LLM behavior unchanged.
4. Ensure the synthesizer output passes through the same unsupported-claim guard and tool-call detection as current LLM responses.
5. Update `PersonaSynthesis` to carry the structured response fields.
6. Update tests and documentation together with the implementation.

## Not Now

- Full multi-persona orchestration beyond the current bounded skeleton.
- Vector, hybrid, or hosted graph indexes.
- Plugin loading.
- Proactive reflection or notification work.
- Web or GUI interface work.
- Private memory schema migration.
- Dashboard-style or dependency-heavy terminal UI.

## Completion Criteria

- Activated turns use the synthesizer output as the user-facing response.
- Non-activated turns keep current single-LLM behavior.
- The synthesizer response schema matches `ParsedChatResponse` (answer, evidence_references, confidence, epistemic_status).
- Unsupported-claim guard and tool-call detection still apply.
- Persona internals do not leak into CLI or daemon payloads.
- All operations are type-checked and tested.
- README TODOs track completed progress, while this file stays limited to the active goal.
