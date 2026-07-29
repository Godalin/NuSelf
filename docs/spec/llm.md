# LLM-Driven Decisions Spec

## Shared Agent Invocation

Framework-native generated-output capabilities live under `nuself.agent`.
`StructuredAgent` owns exact Pydantic results and `TextAgent` owns non-empty
natural-language results. Both receive LangChain `BaseMessage` sequences.

Configured endpoint iteration, availability classification, redacted
diagnostics, active-endpoint persistence, exhaustion errors, and component
attribution are implemented once by the shared agent endpoint invocation
primitive. Capability runners provide only the endpoint-specific framework
call and result validation; they must not own another retry loop.

Provider error diagnostics must remove credential-like values before applying
the 500-character length bound. This includes case-insensitive labeled API
keys, tokens, passwords, secrets, authorization values, bearer credentials,
credential-bearing URL query parameters, and common raw provider-key prefixes.
Retry and availability classification may inspect the original provider
exception; only the diagnostic projection is sanitized. Redaction must retain
non-sensitive context needed to identify the endpoint failure.

The shared agent boundary exposes distinct failure classes:

- `AgentModelUnavailableError`: no configured endpoint or every eligible
  endpoint failed availability checks;
- `AgentProtocolError`: the framework returned a state that does not satisfy
  the expected response envelope;
- `AgentInvalidOutputError`: the envelope exists but its generated text or
  structured value is empty or has the wrong schema.

Provider availability classification uses exception types and structured HTTP
status attributes across the exception chain. Authentication, permission,
payment, rate-limit, connection, and timeout failures are eligible. Exception
message text and response-body substrings are never classification inputs.
Protocol and invalid-output errors never trigger endpoint failover.

`TextAgent` invokes the LangChain chat model directly because natural-language
persona conclusions are the intended result. It must not create a fake
single-field schema merely to reuse structured output, and it rejects an empty
or non-text conclusion.

Conversation compression is an auxiliary persistence optimization. When a
configured compression `TextAgent` raises any `Exception`, the turn must still
finish persistence using the deterministic local summary. The failure emits
one `chat/compression_fallback` audit with required safe error diagnostics and
no metadata. Missing compression-agent configuration uses the same local
summary but is a normal mode and emits no degradation audit.

## Overview

This spec defines the behavioral contracts for replacing hardcoded heuristic scoring with LLM-driven contextual decisions across NuSelf. All L2 (judgment-layer) decisions follow the same pattern: the system assembles a structured prompt with full context, calls the LLM with a strict output schema, and uses the returned values as the decision.

## Decision Pattern

Every L2 decision point uses the same implementation pattern:

```text
1. Gather context (candidate, history, user state, time)
2. Build a structured system prompt describing the decision task
3. Call LLM with a JSON output schema
4. Parse and validate the structured response
5. Fall back to safe defaults if parsing fails
6. Log the decision with reasoning for traceability
```

## P0: LLMRelevanceGate

### Deleted Behavior

The old `RelevanceGate` class has been deleted. It previously:

1. Computed novelty via crude string matching against last reflection:
   - `title == last_title → 0.0`
   - `body == last_body → 0.1`
   - `body in last_body or last_body in body → 0.5`
   - otherwise `1.0`
2. Computed composite via weighted formula:
   `novelty*0.25 + confidence*0.20 + urgency*0.25 - interruption_cost*0.15 + cooldown_ok*0.15`
3. Applied hard veto: `not (interruption_cost >= 0.9 and urgency < 0.5)`
4. Returns `RelevanceScore` with all fields

### New Behavior

`LLMRelevanceGate.score(candidate)` shall:

1. Read the last N reflections (N=3) from `ReflectionRepository` for semantic context
2. Build a system prompt containing:
   - The candidate (title, body, type, confidence, novelty, urgency, interruption_cost)
   - Recent reflection history (titles and bodies)
   - Current time and cooldown state
3. Request structured JSON output:
   ```json
   {
     "novelty": 0.0-1.0,
     "confidence": 0.0-1.0,
     "urgency": 0.0-1.0,
     "interruption_cost": 0.0-1.0,
     "composite": 0.0-1.0,
     "passes": true|false,
     "reason": "explanation of the judgment"
   }
   ```
4. Clamp all floats to [0, 1]
5. `passes` is the LLM's holistic judgment, not a derived formula
6. On parse failure, fall back to `RelevanceScore` with `passes=false`, `composite=0.0`, and `reason="llm_fallback"`

### Prompt Design

```
You are the Relevance Gate for a private AI mirror. Your job is to judge whether a
newly generated reflection idea is worth surfacing to the user right now.

Candidate idea:
- Title: {title}
- Body: {body}
- Type: {type}
- Original scores: confidence={c}, novelty={n}, urgency={u}, interruption={i}

Recent reflection history (last {n} ideas):
{history}

Current state:
- Cooldown active: {yes/no}
- Time: {iso_timestamp}

Judge:
1. NOVELTY (0-1): Is this genuinely new relative to recent reflections? Consider semantic meaning, not just string similarity. A variant of an old topic can still be novel if it brings a new angle.
2. CONFIDENCE (0-1): How well-supported is this idea by the user's memory and conversations?
3. URGENCY (0-1): How time-sensitive is this? Should the user see it soon?
4. INTERRUPTION_COST (0-1): How disruptive would it be to interrupt the user with this now?
5. COMPOSITE (0-1): Your overall assessment of the idea's value.
6. PASSES (true/false): Should this idea be allowed through the gate?
7. REASON: A brief sentence explaining your judgment.

Return ONLY a JSON object with the fields above. No markdown fences.
```

### Interface

```python
class LLMRelevanceGate:
    def __init__(
        self,
        project_root: Path | None = None,
        config: ReflectionSettings | None = None,
        relevance_agent: ReflectionRelevanceAgent | None = None,
    ) -> None:
        ...

    def score(self, candidate: IdeaCandidate) -> RelevanceScore:
        ...

    def _cooldown_ok(self) -> bool:
        # Uses config.scheduler.cooldown_seconds (L1 policy), not hardcoded 300
        ...
```

### Backward Compatibility

- The old `RelevanceGate` class is deleted.
- `ReflectionScheduler` instantiates `LLMRelevanceGate` instead.
- Tests use a `FakeLLM` that returns deterministic JSON responses.

## P1: Persona Activation + Host Escalation

### Deleted Behavior

The old `PersonaActivationPolicy` and `HostDiscussionPolicy` classes have been deleted.

- `PersonaActivationPolicy.decide()`: hardcoded keyword-marker matching (`_skeptic_markers`, `_builder_markers`, etc.) + length heuristic (`>= 180` and `?`)
- `HostDiscussionPolicy.decide()`: keyword matching + `len(message) >= 180` + `len(selected) >= 2`

### New Behavior

A single `AgentBackedActivationPolicy` replaces both. One typed agent call decides:
1. **Which personas** should respond to the user's message
2. **Whether** the topic warrants competitive multi-persona discussion

`AgentBackedActivationPolicy.decide(persona_input)` shall:

1. Receive: user message + memory context + available persona list (id + description)
2. Build framework-native system and human messages describing each persona
   and the user's context
3. Invoke the exact `PersonaActivationOutput` schema through
   `PersonaGraphAgents.activation`:
   ```json
   {
     "activated": true|false,
     "selected_persona_ids": ["analyst_self", "skeptic_self"],
     "trigger": "reason_for_activation",
     "should_escalate": true|false,
     "escalation_reason": "why competitive discussion is warranted"
   }
   ```
4. Map `selected_persona_ids` back to `PersonaDefinition` objects
5. `activated` is true if `selected_persona_ids` is non-empty
6. On agent or schema failure, fall back to
   `PersonaActivation(trigger="agent_fallback")`

### Prompt Design

```
You are the Persona Activation Gate for NuSelf, a private AI mirror.
Your job is to decide which internal thought selves (personas) should
respond to the user's message, and whether the topic warrants a
competitive multi-persona discussion.

Available personas:
{for each persona}
- {persona_id}: {description}
{end}

User message: {user_message}
Memory context: {memory_context}

Return these structured fields:
- activated (bool): Should any personas respond?
- selected_persona_ids (list): Which personas are relevant? Empty if none.
- trigger (string): Brief reason for the selection.
- should_escalate (bool): Should this enter competitive multi-persona discussion?
- escalation_reason (string): Brief reason for escalation.

```

### Interface

```python
@dataclass(frozen=True)
class PersonaActivation:
    trigger: str
    selected_personas: tuple[PersonaDefinition, ...] = ()
    should_escalate: bool = False
    escalation_reason: str = ""

    @property
    def activated(self) -> bool:
        return bool(self.selected_personas)


class AgentBackedActivationPolicy:
    def __init__(
        self,
        personas: tuple[PersonaDefinition, ...] | None = None,
        agent: StructuredAgent[PersonaActivationOutput] | None = None,
    ) -> None: ...

    def decide(self, persona_input: PersonaInput) -> PersonaActivation: ...
```

### Backward Compatibility

- The old `PersonaActivationPolicy` and `HostDiscussionPolicy` classes are deleted.
- `ConversationGraphRuntime` instantiates `AgentBackedActivationPolicy` instead.
- `run_personas_node` reads `state.persona_activation.should_escalate` directly; no second policy call.
- Tests use deterministic typed agents.
- `render_host_decision` no longer displays `matched_markers`; it uses `escalation_reason` from log metadata.

## P2: Persona Discussion Scoring

### Current Behavior (to replace)

- `_heuristic_score()`: ~30 lines of hardcoded persona-specific adjustments (`skeptic` downscores interruption, `builder` upscores action, etc.)
- `_round_has_consensus()`: hard thresholds (`composite >= 0.4`, `spread <= 0.15`, `support >= 2`)
- `_maybe_spawn_emergent_persona()`: hardcoded `novelty >= 0.7` / `urgency >= 0.8`
- `_select_personas()`: random selection
- `_participants_for_turn()`: random subset each turn

### New Behavior

#### 1. Participant Selection (`_select_personas_with_llm`)

An LLM call receives the candidate and available persona list, returns the most relevant persona IDs.

```json
{
  "selected_persona_ids": ["analyst_self", "skeptic_self", "builder_self"],
  "reason": "analytical question with implementation implications"
}
```

Fallback: return first `max_participants` non-synthesizer personas.

Each discussion turn uses the selected personas deterministically, capped at `max_participants`. If the moderator requests an emergent persona, the next turn keeps up to `max_participants - 1` selected personas and includes the temporary persona in the remaining slot. Random participant sampling is deleted.

#### 2. Persona Scoring (`AgentBackedScoringPersonaNode`)

Each persona node prompt now requests both a note and a 0-1 score:

```json
{
  "note": "1-2 sentence perspective from this persona",
  "score": 0.75
}
```

The score is stored in `PersonaContribution.confidence`. `_heuristic_score()` is deleted; the raw LLM-reported score is used directly.

Fallback: note = "{persona_id} considered the topic.", score = 0.5.

For the standard persona graph, structured endpoint, contribution completion,
synthesis completion, and activation failures are recorded through shared
best-effort observability. These diagnostics never replace the fallback or
prevent another configured structured endpoint from being tried.

Standard persona fallback eligibility uses the shared agent failure policy.
Provider/runtime and validation failures retain deterministic fallback, while
sharedly classified implementation and process-integrity failures propagate
rather than becoming neutral persona output.

Competitive persona discussion uses the same observability boundary for
scoring, participant-selection, and moderator-judgment failures. Its neutral
score, deterministic participant pool, and non-converged moderator fallbacks
remain authoritative when diagnostic persistence fails.

#### 3. Moderator Judgment (`_moderator_judgment`)

Replaces both `_round_has_consensus()` and `_maybe_spawn_emergent_persona()`. After each scoring round, the moderator LLM receives the current scores and discussion trace, then returns:

```json
{
  "converged": true|false,
  "emergent_persona": "bridge_self|urgency_self|none",
  "reason": "assessment of the discussion state"
}
```

- `converged`: has the discussion reached a stable conclusion?
- `emergent_persona`: should a bridge (for contradictions/connections) or urgency (for high-urgency questions) persona join the next round?

Fallback: `converged=false`, `emergent_persona="none"`.

#### 4. Approval Logic (unchanged mechanics)

After the discussion loop exits, the same deterministic rules apply:
- Blocking veto: any score < `blocking_threshold` with fewer than 2 scores > `override_threshold` → reject
- Composite threshold: average score < `composite_threshold` → reject
- Otherwise → approve, winners are personas with score >= composite average

### Prompt Designs

**Participant Selection:**
```
You are the Discussion Host. Select the 3-5 most relevant personas to discuss this reflection idea.

Available personas:
{list}

Candidate: {title}
{body}
Type: {type} | Confidence: {confidence} | Novelty: {novelty} | Urgency: {urgency}

Return ONLY JSON: {"selected_persona_ids": [...], "reason": "..."}
No markdown fences.
```

**Scoring Persona Node:**
```
You are {persona_id}. Role: {description}

Candidate: {title}
{body}
Type: {type} | Confidence: {confidence} | Novelty: {novelty} | Urgency: {urgency} | Interruption: {interruption_cost}

Give your perspective (1-2 sentences) AND a score (0.0-1.0) for how strongly you support this idea.

Return ONLY JSON: {"note": "...", "score": 0.7}
No markdown fences.
```

**Moderator Judgment:**
```
You are the moderator. Current scores:
{persona_id}: {score}
...

Discussion trace:
{trace}

Turn {turn_number} of {max_turns}.

Has the discussion converged? Should an emergent persona join?
Return ONLY JSON: {"converged": true|false, "emergent_persona": "bridge_self|urgency_self|none", "reason": "..."}
No markdown fences.
```

## Error Handling

All L2 decisions must:

- Catch `json.JSONDecodeError`, `RuntimeError` (LLM failure), and `KeyError` (missing fields)
- Fall back to safe defaults on any failure
- Log the failure with context for debugging
- Never block the calling pipeline because of an LLM failure

## Testing Strategy

- Use `FakeLLM` with deterministic JSON responses for unit tests
- Test fallback behavior by providing malformed JSON
- Test boundary conditions (empty history, maxed-out scores)
- Keep golden fixtures for each decision point
