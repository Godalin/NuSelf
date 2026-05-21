# Final Response Boundary Spec

## Purpose

The final response boundary is the runtime guard that decides whether a chat agent draft is safe to show to the user.

NuSelf no longer uses a separate LLM-backed presentation agent in the normal chat path. The chat supervisor is responsible for both tool/subagent orchestration and final user-facing wording. This avoids an extra model call and keeps tool results, selves output, and final wording in one agent context.

The boundary is not a sanitizer. It does not mechanically edit leaked protocol text. It checks the structured chat output and, when needed, asks the same chat supervisor to regenerate once with a stricter final-answer instruction. The runtime may still robustly parse protocol-shaped model responses, including fenced JSON protocol blocks, because protocol parsing is transport handling rather than answer rewriting.

## Pipeline Position

The conversation pipeline should end with:

```text
chat supervisor / tool / subagent loop
→ DraftResponse
→ final response boundary
→ PresentedResponse
→ final_response
→ state_update
```

Only `PresentedResponse.answer` is saved as the assistant turn, returned by the daemon, printed in the REPL, and included as the normal chat reply in transcript exports.

Internal drafts, persona contributions, protocol details, and tool traces may be logged, but they are not normal assistant messages.

## DraftResponse Contract

`DraftResponse` is internal.

Required fields:

| Field | Type | Meaning |
|---|---|---|
| `draft_answer` | `str` | The substantive answer content before final presentation |
| `evidence_references` | `tuple[str, ...]` | Memory/source refs supporting the answer |
| `epistemic_status` | `str` | `grounded` \| `inferred` \| `uncertain` \| `unsupported` |
| `confidence` | `float \| None` | Optional confidence estimate |

Optional fields:

| Field | Type | Meaning |
|---|---|---|
| `presentation_hints` | `tuple[str, ...]` | Style and length cues inferred by the thinking stage |
| `internal_notes` | `str` | Private context for presentation; never copied verbatim |

## PresentedResponse Contract

`PresentedResponse` is user-facing.

Required fields:

| Field | Type | Meaning |
|---|---|---|
| `answer` | `str` | Final user-facing Markdown text |
| `evidence_references` | `tuple[str, ...]` | Same refs as draft unless presentation explicitly drops unsupported material |
| `epistemic_status` | `str` | Same or more cautious than draft |
| `confidence` | `float \| None` | Same or lower than draft unless omitted |

`answer` must not contain:

- raw JSON protocol objects;
- Markdown code fences used to show the response protocol;
- protocol field names such as `evidence_references` or `epistemic_status`;
- internal persona attribution such as `synthesizer_self combined analyst_self`;
- raw tool-call payloads, including `[Tool call: ...]` markers.

## Prompt Requirements

The ordinary chat supervisor prompt must include the final-answer boundary:

- output only the required structured response for the runtime;
- keep `answer` as plain user-facing Markdown;
- do not include raw tool calls, protocol JSON, or persona attribution in `answer`;
- adapt length and structure to the user's current state;
- keep uncertainty explicit.

When the active chat model is available through LangChain, the final chat result must be requested through LangChain structured output (`with_structured_output(...)` or an equivalent `response_format`) after any tool loop completes. Prompted JSON parsing is only a compatibility fallback for deterministic tests and non-LangChain local fallback models.

## Quality Retry

If `DraftResponse.answer` violates the user-facing boundary, the runtime should ask the same chat supervisor to regenerate once with the same context and a stricter instruction.

Boundary checks may detect:

- `answer` starts with `{` and contains protocol-looking fields such as `answer`, `evidence_references`, `confidence`, or `epistemic_status`, even when the object is pretty-printed or not valid JSON;
- `answer` starts with a Markdown code fence;
- `answer` contains raw tool-call markers such as `[Tool call: ...]` anywhere in the visible text;
- `answer` contains multiple response protocol field names near the beginning or in the first visible protocol-shaped block;
- `answer` starts with internal persona attribution.

These checks only decide whether to retry. They must not rewrite the answer.

If the retry fails, the runtime may fall back to the original draft answer only when that draft itself satisfies the user-facing boundary. If both the retry and draft are invalid, the runtime returns a short boundary-failure message and logs `final_response_failed`; it must not save or display raw protocol JSON as the assistant answer.

## Prompt Context Hygiene

The runtime may contain older assistant messages saved before the current boundary rules existed. When building prompt context for a new turn, it must exclude assistant history messages that violate the same user-facing boundary, including visible `[Tool call: ...]` markers and raw response-protocol JSON. The original persisted thread may remain unchanged for audit/export purposes; the polluted message must simply not be used as an example for future model behavior.

## Logging

Final response boundary events use the `chat` log component:

| Event | Status | Meaning |
|---|---|---|
| `final_response_completed` | `completed` | Draft accepted as final answer |
| `final_response_retry` | `retry` | Draft violated the boundary and was regenerated |
| `final_response_failed` | `failed` | Retry was unavailable or invalid |

Logs may include short metadata such as `thread`, `retry_reason`, `epistemic_status`, and `duration_ms`. Logs must not include full private draft text by default.

## Applicability

Use the final response boundary for:

- normal chat answers;
- persona-synthesized chat answers;
- tool follow-up answers;
- future surfaced reflection prose when it is delivered as conversational text.

Do not use the final response boundary for:

- deterministic CLI list/show records;
- logs;
- durable memory writes;
- raw transcript preservation.

## Fallback Policy

The final response boundary should fail soft:

1. invalid draft output → retry once through the same chat supervisor;
2. retry invalid or LLM unavailable → use draft answer only if the draft is user-facing safe;
3. invalid draft fallback → return a short boundary-failure message;
4. log the failure;
5. never crash an otherwise successful chat turn solely because final-answer regeneration failed.
