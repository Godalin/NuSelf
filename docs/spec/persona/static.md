# Static Persona System Spec

Status: implemented (v0.2.0).

## Purpose

The static persona system provides a fixed set of built-in thinking roles
(`analyst_self`, `skeptic_self`, …) and a LangGraph subgraph that runs them.
These are hardcoded roles with fixed `id` + `description`. They do not evolve
and cannot be created or modified at runtime.

For dynamic user-authored thinking personas, see [dynamic.md](dynamic.md).
For competitive multi-persona discussion, see [discussion.md](discussion.md).

## Data Models

```python
@dataclass(frozen=True)
class PersonaDefinition:
    id: str              # e.g. "analyst_self"
    description: str     # e.g. "Decomposes a question into concepts…"

@dataclass(frozen=True)
class PersonaInput:
    user_message: str
    memory_context: str = ""   # prior discussion or context

@dataclass(frozen=True)
class PersonaContribution:
    persona_id: str
    notes: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    confidence: float | None = None

@dataclass(frozen=True)
class PersonaSynthesis:
    summary: str
    source_personas: tuple[str, ...] = ()
    confidence: float | None = None
    answer: str | None = None
    evidence_references: tuple[str, ...] = ()
    epistemic_status: str | None = None

@dataclass(frozen=True)
class PersonaActivation:
    trigger: str
    selected_personas: tuple[PersonaDefinition, ...] = ()
    should_escalate: bool = False
    escalation_reason: str = ""
    # property: activated → bool(selected_personas)

@dataclass(frozen=True)
class PersonaTurnState:
    input: PersonaInput
    selected_personas: tuple[PersonaDefinition, ...]
    contributions: tuple[PersonaContribution, ...] = ()
    synthesis: PersonaSynthesis | None = None
    node_trace: tuple[str, ...] = ()
```

### Pydantic Structured-Output Models

Used only by LLM-backed graph nodes (not by the minimal fallbacks):

- `PersonaContributionOutput`: `note`, `questions`, `confidence`
- `PersonaSynthesisOutput`: `summary`, `confidence`
- `PersonaActivationOutput`: `activated`, `selected_persona_ids`, `trigger`, `should_escalate`, `escalation_reason`

## Builtin Personas

| Constant | id | Role |
|---|---|---|
| `ANALYST_PERSONA` | `analyst_self` | Decomposes questions into concepts, assumptions, implications |
| `SKEPTIC_PERSONA` | `skeptic_self` | Challenges assumptions, risks, missing counter-evidence |
| `BUILDER_PERSONA` | `builder_self` | Turns intent into practical steps, milestones, execution |
| `HISTORIAN_PERSONA` | `historian_self` | Connects prior context and timelines to current decisions |
| `CARE_PERSONA` | `care_self` | Highlights emotional impact, support, sustainable pacing |
| `SYNTHESIZER_PERSONA` | `synthesizer_self` | Fuses contributions into compact synthesis (internal only) |
| `MODERATOR_PERSONA` | `moderator_self` | Keeps discussion converging (competitive discussion only) |

`BUILTIN_PERSONAS` tuple contains the first 5 (excludes synthesizer and moderator).

## Persona Graph (`PersonaGraphDriver`)

A LangGraph `StateGraph` with two sequential nodes:

```
START → run_personas → run_synthesizer → END
```

- **run_personas**: Runs each selected persona through `PersonaNode`, collects contributions
- **run_synthesizer**: Runs `PersonaSynthesizerNode` over contributions, produces synthesis

The driver accepts injectable `PersonaNode` and `PersonaSynthesizerNode` implementations.

## Node Implementations

### Protocol

```python
class PersonaNode(Protocol):
    def __call__(self, persona: PersonaDefinition, persona_input: PersonaInput) -> PersonaContribution: ...

class PersonaSynthesizerNode(Protocol):
    def __call__(self, turn_state: PersonaTurnState) -> PersonaSynthesis | None: ...
```

### Minimal (deterministic, no LLM)

- **MinimalPersonaNode**: Generates a deterministic template utterance per persona id
- **MinimalSynthesizerNode**: Concatenates first notes from each contribution

### Agent-Backed

`PersonaGraphAgents` composes exact-schema activation, contribution, and
synthesis agents through the shared framework-native structured-agent runner.

- **AgentBackedPersonaNode**: generates a distinct typed contribution for a
  persona id, description, topic, and prior discussion.
- **AgentBackedSynthesizerNode**: distills contributions into a typed one- or
  two-sentence synthesis.
- **AgentBackedActivationPolicy**: decides which personas activate and whether
  competitive discussion should run.
- **AgentBackedScoringPersonaNode** (discussion only): returns both a typed note
  and a support score.

The graph does not own endpoint iteration, call `with_structured_output`
directly, request JSON, parse final message text, or accept dictionaries.
Shared runner failures are observable at that boundary; each graph node then
records its stage-specific fallback and returns the existing deterministic
domain result. Diagnostic persistence cannot replace fallback output.

### Activation Policy

`AgentBackedActivationPolicy` decides whether persona work should run for a turn:

```
decide(persona_input) → PersonaActivation
```

The policy:
1. Checks if an agent is available (`trigger="no_agent"` when absent).
2. Invokes the exact `PersonaActivationOutput` agent.
3. On any error, returns safe fallback (`trigger="agent_fallback"`, no
   activation).

Activation errors also write `persona_activation_failed` before returning that
safe fallback. Diagnostic failure cannot replace or alter the activation
result.

The three output models are strict, extra-forbid, and complete: contribution
and synthesis confidence is required in `[0, 1]`; activation requires every
decision field; text and persona ids are normalized non-blank strings; and
activation state must be internally consistent. A dictionary or malformed
item cannot cross the shared typed boundary.

The activation result surfaces:
- **`selected_personas`**: Which built-in personas should respond
- **`should_escalate`**: Whether the topic warrants competitive multi-persona discussion

## Dynamic Definition Loading

`load_persona_definitions(project_root)` loads custom persona definitions from
durable memory entries with `type="persona_instruction"`. These entries must have
payload fields `persona_id` and `description`. Falls back to `BUILTIN_PERSONAS` when
no memory entries exist or on error.

## Source

- `src/nuself/persona/definition.py` — data models, protocols, builtins
- `src/nuself/persona/graph.py` — graph driver, node implementations
