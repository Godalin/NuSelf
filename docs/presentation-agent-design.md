# Presentation Agent Design

## Motivation

NuSelf currently asks the conversation agent to do too many jobs at once:

1. understand the user's intent,
2. retrieve and interpret memory,
3. run persona synthesis and tool calls,
4. produce a protocol-compliant structured response,
5. make the final user-facing text pleasant, concise, and readable.

Recent failures, such as raw response JSON appearing in the REPL or internal persona attribution appearing at the start of an answer, are symptoms of this mixed responsibility. The better design is not to mechanically clean bad text after the fact. The better design is to split thinking from presentation and let a dedicated LLM-backed output stage handle user-facing expression.

## Principle

Presentation is an L2 judgment task.

The system can deterministically detect obvious boundary failures, such as protocol JSON leaking into a user-visible answer, but it should not rewrite the answer with string surgery. Instead, the LLM should be asked to produce the final expression under a clear presentation contract.

This extends the existing LLM-driven decision architecture:

- **Thinking agent**: decides what should be said.
- **Presentation agent**: decides how it should be said to this user right now.
- **Deterministic renderer**: displays already-final text and structured records without changing meaning.

## Proposed Conversation Pipeline

```text
prepare_context
→ persona_activation
→ run_personas
→ thinking_response
→ detect_tool_request
→ execute_tool
→ revise_thinking_response
→ presentation_agent
→ final_response
→ state_update
→ compression
```

The names can change during implementation, but the boundary should remain:

- Everything before `presentation_agent` may use tools, memory, persona traces, evidence metadata, and structured intermediate fields.
- `presentation_agent` receives an internal draft plus metadata and produces the only user-facing answer text.
- `final_response` is what gets saved to thread history, returned to the daemon, printed in the REPL, and included in transcript chat turns.

## Data Boundary

The thinking stage should return an internal object, not final prose:

```python
DraftResponse:
    draft_answer: str
    evidence_references: tuple[str, ...]
    confidence: float | None
    epistemic_status: str
    tool_request: ConversationToolCall | None
    presentation_hints: tuple[str, ...]
    internal_notes: str
```

Only these fields may flow into the presentation prompt:

- `draft_answer`
- `evidence_references`
- `confidence`
- `epistemic_status`
- recent user message and compact conversation context
- user style signals, such as "simple", "shorter", "I am overwhelmed"
- bounded presentation hints

Internal persona traces, raw tool protocol details, and model reasoning are not part of the user-facing answer. They can still be logged and exported when log scope allows them.

## Presentation Agent Contract

The presentation agent:

- may rewrite, shorten, structure, and soften the draft;
- may choose Markdown shape for readability;
- may adapt to the user's current cognitive load and language preference;
- must preserve factual content, evidence references, and epistemic status;
- must not add new claims, memories, or tool results;
- must not expose protocol JSON, field names, raw tool calls, or internal persona attribution;
- must not hide uncertainty that the thinking stage marked as important.

If the user asks for "simple", "short", "I cannot think through this", or similar, the presentation agent should prioritize compression and one-step structure over completeness.

## Failure Handling

Presentation failures should be handled by asking the model to regenerate once with a stricter presentation instruction. The system may detect obvious failures, but should not manually transform the answer into a different answer.

Safe fallback:

1. If the presentation agent is unavailable or returns invalid structured output, use the draft answer.
2. Log `presentation_failed` with the reason.
3. If the draft itself leaks protocol or internal traces, ask the thinking stage or presentation stage to regenerate once before falling back.

The fallback is a reliability mechanism, not the main design.

## Other Places This Pattern Applies

The split is useful wherever NuSelf has both internal judgment and user-facing expression:

| Area | Apply presentation split? | Reason |
|---|---:|---|
| Chat replies | Yes | Main source of persona/protocol leakage and tone mismatch |
| Tool follow-up answers | Yes | Tool results are raw context; final wording should be separate |
| Reflection ideas surfaced in chat | Yes, later | Candidate generation can stay exploratory; surfaced wording should be concise |
| Notification titles/bodies | Maybe | Notifications need brief human wording, but should remain cheap and predictable |
| Transcript export | No for chat turns, maybe for summaries | Export should preserve actual final replies; optional share summaries can use a presentation pass |
| CLI list/show records | No | These are deterministic structured renderers, not generative prose |
| Memory curator/optimizer writes | No for persistence, maybe for review previews | Durable memory needs structured actions; preview text may benefit from presentation |
| Logs | No | Logs are audit records and should not be rewritten as prose |

## Implementation Slices

1. **Spec and design only**: document the split and decide the contracts.
2. **Introduce `DraftResponse` / `PresentedResponse` types** without changing behavior.
3. **Route ordinary chat through presentation agent** with fake-LLM tests.
4. **Route tool follow-up through presentation agent**.
5. **Move the current protocol-leak retry into the presentation stage**.
6. **Add logs**: `presentation_started`, `presentation_completed`, `presentation_retry`, `presentation_failed`.

## Open Design Questions

- Should presentation be optional in config for low-latency mode?
- Should presentation use the same LLM as thinking, or a cheaper/faster model when configured?
- Should user style preferences be stored as memory and explicitly retrieved for presentation?
- Should presentation logs be included in default transcript exports, or only with `:export all`?
