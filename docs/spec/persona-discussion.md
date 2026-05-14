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

When no LLM is configured, the system falls back to **MinimalPersonaNode** / **MinimalSynthesizerNode**, which produce deterministic placeholder utterances.

`persona_summary` logs are ordinary activated self passes. They are not proof that competitive discussion ran. Competitive chat discussion only runs when `LLMBackedActivationPolicy.should_escalate` is true; otherwise the host decision log is `status=skipped`.

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

Renderers must parse these prefixes and group by turn. See [`cli-interaction.md`](cli-interaction.md) for trace rendering contract.

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
