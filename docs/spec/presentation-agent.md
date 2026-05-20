# Presentation Agent Spec

## Purpose

The presentation agent is the final LLM-backed user-facing expression stage for chat answers. It separates "what NuSelf has decided to say" from "how NuSelf says it to the user right now."

The presentation agent is not a sanitizer. It does not mechanically edit leaked protocol text. It receives a structured internal draft and generates a fresh final answer under a strict presentation contract. The runtime may still robustly parse protocol-shaped model responses, including fenced JSON protocol blocks, because protocol parsing is transport handling rather than answer rewriting.

## Pipeline Position

The conversation pipeline should end with:

```text
thinking/tool/persona stages
→ DraftResponse
→ PresentationAgent.present()
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

The presentation prompt must include:

1. the current user message;
2. compact recent conversation context when available;
3. the draft answer;
4. evidence refs, confidence, and epistemic status;
5. language preference;
6. presentation hints, including signs of cognitive overload or requests for brevity.

The prompt must instruct the model:

- preserve the draft's factual content;
- do not add new facts, memories, citations, or tool results;
- adapt length and structure to the user's current state;
- output only the required structured response for the runtime;
- keep `answer` as plain user-facing Markdown.

## Quality Retry

If `PresentedResponse.answer` violates the user-facing boundary, the runtime should ask the presentation agent to regenerate once with the same draft and a stricter instruction.

Boundary checks may detect:

- `answer` starts with `{` and contains protocol-looking fields such as `answer`, `evidence_references`, `confidence`, or `epistemic_status`, even when the object is pretty-printed or not valid JSON;
- `answer` starts with a Markdown code fence;
- `answer` contains multiple response protocol field names near the beginning or in the first visible protocol-shaped block;
- `answer` starts with internal persona attribution.

These checks only decide whether to retry. They must not rewrite the answer.

If the retry fails, the runtime may fall back to the original draft answer only when that draft itself satisfies the user-facing boundary. If both presentation and draft are invalid, the runtime returns a short boundary-failure message and logs `presentation_failed`; it must not save or display raw protocol JSON as the assistant answer.

## Logging

Presentation events use the `chat` log component:

| Event | Status | Meaning |
|---|---|---|
| `presentation_started` | `started` | Presentation stage began |
| `presentation_completed` | `completed` | Final answer generated |
| `presentation_retry` | `retry` | First presentation violated the boundary |
| `presentation_failed` | `failed` | Presentation unavailable or invalid after retry |

Logs may include short metadata such as `thread`, `retry_reason`, `epistemic_status`, and `duration_ms`. Logs must not include full private draft text by default.

## Applicability

Use the presentation agent for:

- normal chat answers;
- persona-synthesized chat answers;
- tool follow-up answers;
- future surfaced reflection prose when it is delivered as conversational text.

Do not use the presentation agent for:

- deterministic CLI list/show records;
- logs;
- durable memory writes;
- raw transcript preservation.

## Fallback Policy

The presentation stage should fail soft:

1. invalid presentation output → retry once;
2. retry invalid or LLM unavailable → use draft answer only if the draft is user-facing safe;
3. invalid draft fallback → return a short boundary-failure message;
4. log the failure;
5. never crash an otherwise successful chat turn solely because presentation failed.
