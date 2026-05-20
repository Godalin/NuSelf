# Persona Discussion Spec

## Competitive Discussion Flow

```
select_personas() → 3–5 random non-synthesizer personas
maybe_spawn_emergent_persona() → bridge_self | urgency_self | None

for turn in 1..max_turns:
    moderator_prompt() → host note appended to trace
    score_candidate(participants) → round_scores
    if round_has_consensus(round_scores):
        append "reached convergence"
        break
    if turn < max_turns:
        append "moderator invites another pass"

evaluate(blocking, strong_support, composite)
```

## Persona Node Implementation

When an LLM is available, both ordinary chat self passes and competitive discussions use **LLM-backed nodes**:

- **LLMBackedPersonaNode**: Prompts the LLM with the persona's `id` and `description`, plus the current topic and prior discussion context. Each persona generates a 1–2 sentence response from its unique perspective. Later personas in the same turn see earlier personas' contributions and can build on or challenge them.
- **LLMBackedSynthesizerNode**: Prompts the LLM to distill the turn's contributions into a 1–2 sentence summary capturing consensus or key tension.
- **LLMBackedActivationPolicy**: Decides activation and escalation through LangChain structured output when a LangChain chat model is available.

LLM-backed persona activation, persona notes, and synthesis must request structured data through LangChain structured output (`with_structured_output(...)` or equivalent response-format support) when available. Prompted JSON parsing is a compatibility fallback for deterministic tests and non-LangChain local fallback models.

When no LLM is configured, the system falls back to **MinimalPersonaNode** / **MinimalSynthesizerNode**, which produce deterministic placeholder utterances.

`persona_summary` logs are ordinary activated self passes. They are not proof that competitive discussion ran. Competitive chat discussion only runs when `LLMBackedActivationPolicy.should_escalate` is true; otherwise the host decision log is `status=skipped`.

## User-Facing Boundary

Persona contributions and synthesis are internal context for answer generation. User-facing assistant replies should present the synthesized answer directly as NuSelf. They should not narrate internal persona composition, such as "synthesizer_self combined analyst_self and builder_self", unless the user explicitly asks about the internal persona mechanism itself.

This boundary is enforced as a prompt-level instruction, not by output sanitization. Persona traces remain visible through logs and transcript exports when those logs are included.

## Language

Competitive discussion traces are user-inspectable logs. LLM-backed participant notes, moderator notes, and synthesis summaries should follow `chat.language_preference` when it is not English, while keeping stable internal identifiers such as `analyst_self` and `turn-1` unchanged.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `min_participants` | `3` | Minimum personas selected |
| `max_participants` | `5` | Maximum personas selected |
| `max_turns` | `12` (from config) | Discussion round limit |
| `blocking_threshold` | `0.35` | Score below this triggers a blocking veto |
| `override_threshold` | `0.7` | Score above this counts as strong support |
| `composite_threshold` | `0.4` | Average score must meet this to approve |
| `consensus_spread_threshold` | `0.15` | Max spread for consensus |

## Emergent Personas

| Condition | Emergent Persona |
|---|---|
| `candidate_type in {connection, contradiction}` AND `novelty >= 0.7` | `bridge_self` |
| `candidate_type == question` AND `urgency >= 0.8` | `urgency_self` |

## Approval Rules

1. **Blocking veto**: If any participant scores `< blocking_threshold` AND `strong_support < 2`, reject.
2. **Composite gate**: If `composite < composite_threshold`, reject.
3. **Winners**: All participants with `score >= composite`.
4. **Consensus shortcut**: If `composite >= threshold` AND `spread <= threshold` AND no blocking AND `strong_support >= 2`, break early.

## Discussion Trace Format

Trace entries are strings with these prefixes:

| Prefix | Format | Meaning |
|---|---|---|
| `candidate:` | `candidate: <title>` | Candidate info header |
| `type=...` | `type=<t> confidence=... novelty=...` | Candidate metadata |
| `<body>` | raw body text | Candidate body |
| `host:` | `host: <note>` | Moderator turn opening |
| `turn-N:<persona>:` | `turn-1:analyst_self: <note>` | Persona utterance |
| `turn-N:synthesis:` | `turn-1:synthesis: <summary>` | Synthesizer summary |
| `turn-N:` | `turn-1: reached convergence` | Turn-level system message |

Renderers must parse these prefixes and group by turn. User-facing discussion trace rendering uses square-bracket tags for the trace title, group headers, and speaker labels, such as `[discussion]`, `[turn-1]`, and `[analyst_self]`. See [`cli-interaction.md`](cli-interaction.md) for trace rendering contract.

Chat-triggered discussion must also stream visible trace entries as `persona_discussion_step` logs while the discussion runs. The final chat-triggered `persona_discussion` log is a summary and must not re-emit the full discussion trace in one delayed block.

## Result Structure

```
PersonaCompetitionResult:
  approved: bool
  winner_persona_ids: tuple[str, ...]
  revised_title: str
  revised_body: str
  scores: dict[str, float]
  blocking_vetos: tuple[str, ...]
  reason: str
  discussion_trace: tuple[str, ...]
  emergent_persona_ids: tuple[str, ...]
```
