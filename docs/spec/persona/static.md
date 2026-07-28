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

### LLM-Backed

- **LLMBackedPersonaNode**: Probes the LLM with persona `id` + `description` + topic +
  prior discussion. Uses LangChain structured output (`PersonaContributionOutput`) when
  available; falls back to `ChatLLM.complete()` + prompted JSON parsing.
- **LLMBackedSynthesizerNode**: Distills a turn's contributions into 1–2 sentences.
  Uses `PersonaSynthesisOutput` structured output when available.
- **LLMBackedScoringPersonaNode** (discussion only): Returns both a note and a 0–1
  support score. Used by `ProactivePersonaDiscussion`, not by the standard graph.

### Activation Policy

`LLMBackedActivationPolicy` decides whether persona work should run for a turn:

```
decide(persona_input) → PersonaActivation
```

The policy:
1. Checks if an LLM is available (no LLM → `trigger="no_llm"`, no activation)
2. Tries structured output (`PersonaActivationOutput`) via LangChain endpoints
3. Falls back to prompted JSON via `ChatLLM.complete()`, validated by the same
   strict `PersonaActivationOutput` schema
4. On any error, returns safe fallback (`trigger="llm_fallback"`, no activation)

`PersonaActivationOutput` is the sole activation parse boundary. JSON booleans
must be booleans, persona IDs must be strings, and all declared field types must
validate as written. The prompted-JSON fallback must not use a second
handwritten parser, coerce string booleans, or partially accept malformed
lists.

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
