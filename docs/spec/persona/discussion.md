# Persona Discussion Spec

See [static.md](static.md) for the builtin persona data models, graph,
activation policy, and node implementations (AgentBackedPersonaNode,
PersonaGraphDriver, etc.).

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

## Chat Subagent Boundary

In chat, `selves` is an agent-facing **synchronous subagent service**, not a mandatory fixed stage of every conversation turn.

The main chat agent is the supervisor. It owns the user-visible conversation context, receives user input, decides which tools or subagents to call, and produces the final reply. The selves system is exposed to that supervisor as a LangChain service tool:

```text
chat supervisor → selves_consult(...) → persona subgraph / competitive discussion → tool result → chat supervisor final reply
```

This follows the LangChain subagent pattern: a subagent is invoked as a tool, runs in isolated context, returns a result to the main agent, and does not speak directly to the user. The main chat agent decides whether to use the returned perspectives and how to combine them with memory, reflection, reason, trace, or other tool results.

Rules:

- Ordinary chat must not automatically run persona activation before tool use.
- Direct tool/status questions should usually call the requested service tools directly, not `selves_consult`.
- `selves_consult` is appropriate for multi-perspective requests, value conflicts, architectural tradeoffs, emotionally loaded reflection, self-model questions, or explicit requests for internal discussion.
- Persona contributions and competitive discussion traces remain internal context for the final answer. The user may see them through logs/transcript export, but the final NuSelf reply should not dump raw persona internals unless explicitly asked.
- Chat-triggered selves activity must be logged as `[selves]` activity and the tool call itself must also be logged through the caller/service format as `[chat] [selves] service_tool_called`.

Internally, the `selves_consult` subagent may reuse the existing persona LangGraph subgraph and competitive discussion service. The public boundary is still the LangChain tool/subagent contract; the old fixed chat graph nodes are transitional plumbing and must not be the primary activation path.

`persona_summary` logs are ordinary activated self passes. They are not proof that competitive discussion ran. Competitive chat discussion only runs when `AgentBackedActivationPolicy.should_escalate` is true; otherwise the host decision log is `status=skipped`.

## User-Facing Boundary

Persona contributions and synthesis are internal context for answer generation. User-facing assistant replies should present the synthesized answer directly as NuSelf. They should not narrate internal persona composition, such as "synthesizer_self combined analyst_self and builder_self", unless the user explicitly asks about the internal persona mechanism itself.

This boundary is enforced as a prompt-level instruction, not by output sanitization. Persona traces remain visible through logs and transcript exports when those logs are included.

## Language

Competitive discussion traces are user-inspectable logs. LLM-backed participant notes, moderator notes, and synthesis summaries should follow `chat.language_preference` when it is not English, while keeping stable internal identifiers such as `analyst_self` and `turn-1` unchanged.

## Structured Output Boundaries

Participant scoring, participant selection, and moderator judgment use three
exact-schema agents composed in `PersonaDiscussionAgents`. Each invokes the
shared framework-native structured-agent boundary and accepts only an actual
`PersonaScoreOutput`, `PersonaSelectionOutput`, or
`ModeratorJudgmentOutput`.

The schemas are strict and extra-forbid. Scores must be floats in `[0, 1]`;
notes and reasons are required and non-empty; selection contains one through
five string persona ids; and emergent persona is exactly `bridge_self`,
`urgency_self`, or `none`. Numeric strings are not scores, string values are
not booleans, and one malformed selection item invalidates the complete
selection. Generated values are not defaulted or clamped.

Discussion prompts use LangChain framework messages. They do not request JSON,
parse response text, or retain a secondary dictionary/fenced-text protocol.
Natural-language synthesis uses the graph's exact-schema
`PersonaSynthesisOutput` agent; it is a separate capability from the three
competitive host-decision agents but follows the same shared invocation
boundary.

Malformed output keeps the existing caller-owned safety behavior:

- scoring contributes a neutral `0.5` score and generic note;
- participant selection uses the deterministic default participant pool;
- moderator judgment remains non-converged, selects no emergent persona, and
  allows the bounded discussion loop to continue.

Agent and schema failures for all three stages write
`persona/persona_discussion_degraded` through shared best-effort observability.
Metadata identifies `scoring`, `selection`, or `moderator`; scoring also names
the persona, selection names the candidate, and moderator names the turn.
`SharedPersonaDiscussionService` passes its project root into the discussion
engine and its LLM-backed graph nodes so these records use the same project
storage as the calling chat or reflection runtime. Diagnostic persistence
failure cannot replace the documented fallback, stop the bounded discussion,
or trigger a hidden LLM/diagnostic retry.

The chat orchestration layer that invokes
`SharedPersonaDiscussionService.discuss(...)` also uses the shared agent
failure policy. A recoverable provider/runtime discussion failure may append
the existing visible `Discussion failed` result and write its audit record.
Sharedly classified implementation and process-integrity failures propagate
unchanged rather than being rendered as a persona conclusion; no
discussion-failure audit is created for those errors.

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

Renderers must parse these prefixes and group by turn. User-facing discussion trace rendering uses square-bracket tags for the trace title, group headers, and speaker labels, such as `[discussion]`, `[turn-1]`, and `[analyst_self]`. See [`cli.md`](../cli.md) for trace rendering contract.

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

## Source

- `src/nuself/persona/discussion.py` — `ProactivePersonaDiscussion`, `SharedPersonaDiscussionService`
