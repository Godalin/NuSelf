"""Minimal internal persona graph skeleton."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph  # type: ignore[reportMissingTypeStubs]


@dataclass(frozen=True)
class PersonaDefinition:
    """A bounded internal persona role."""

    id: str
    description: str


@dataclass(frozen=True)
class PersonaInput:
    """Input available to an internal persona node."""

    user_message: str
    memory_context: str = ""


@dataclass(frozen=True)
class PersonaContribution:
    """Structured internal contribution from one persona."""

    persona_id: str
    notes: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()
    confidence: float | None = None


@dataclass(frozen=True)
class PersonaTurnState:
    """State passed through the minimal persona graph."""

    input: PersonaInput
    selected_personas: tuple[PersonaDefinition, ...]
    contributions: tuple[PersonaContribution, ...] = ()
    node_trace: tuple[str, ...] = ()


class PersonaGraphState(TypedDict):
    """LangGraph state wrapper for a persona turn."""

    turn_state: PersonaTurnState


class PersonaNode(Protocol):
    """Callable shape for one persona node."""

    def __call__(self, persona: PersonaDefinition, persona_input: PersonaInput) -> PersonaContribution: ...


class MinimalPersonaNode:
    """Deterministic placeholder persona node used before LLM-backed personas."""

    def __call__(self, persona: PersonaDefinition, persona_input: PersonaInput) -> PersonaContribution:
        note = f"{persona.id} considered: {persona_input.user_message}"
        return PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0)


class PersonaGraphDriver:
    """Minimal LangGraph-backed persona subgraph."""

    def __init__(self, *, persona_node: PersonaNode | None = None) -> None:
        self._persona_node = persona_node or MinimalPersonaNode()
        graph: Any = StateGraph(PersonaGraphState)
        graph.add_node("run_personas", self._run_personas)
        graph.add_edge(START, "run_personas")
        graph.add_edge("run_personas", END)
        self._graph = graph.compile()

    def run(self, state: PersonaTurnState) -> PersonaTurnState:
        output: object = self._graph.invoke({"turn_state": state})
        if not isinstance(output, dict):
            raise RuntimeError("persona graph returned invalid state")
        graph_state = cast(PersonaGraphState, output)
        return graph_state["turn_state"]

    def _run_personas(self, state: PersonaGraphState) -> PersonaGraphState:
        turn_state = state["turn_state"]
        contributions = tuple(
            self._persona_node(persona, turn_state.input) for persona in turn_state.selected_personas
        )
        return {
            "turn_state": replace(
                turn_state,
                contributions=contributions,
                node_trace=(*turn_state.node_trace, "run_personas"),
            )
        }


ANALYST_PERSONA = PersonaDefinition(
    id="analyst_self",
    description="Decomposes a question into concepts, assumptions, and implications.",
)
