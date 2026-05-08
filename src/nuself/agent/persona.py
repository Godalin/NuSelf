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
class PersonaActivation:
    """Decision about whether persona work should run for a turn."""

    trigger: str
    selected_personas: tuple[PersonaDefinition, ...] = ()

    @property
    def activated(self) -> bool:
        return bool(self.selected_personas)


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
        if persona.id == "skeptic_self":
            note = f"{persona.id} challenged assumptions in: {persona_input.user_message}"
            return PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0)
        if persona.id == "builder_self":
            note = f"{persona.id} proposed concrete steps for: {persona_input.user_message}"
            return PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0)
        note = f"{persona.id} considered: {persona_input.user_message}"
        return PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0)


class PersonaActivationPolicy:
    """Small deterministic gate for the minimal persona slice."""

    _explicit_markers = (
        "multiple perspectives",
        "different perspectives",
        "several perspectives",
        "personas",
        "persona",
        "selves",
        "debate",
        "discuss this",
        "多人格",
        "多角度",
        "几个角度",
        "不同视角",
        "讨论一下",
    )
    _depth_markers = (
        "tradeoff",
        "trade-off",
        "decision",
        "long-term",
        "architecture",
        "strategy",
        "should i",
        "取舍",
        "决策",
        "长期",
        "规划",
        "架构",
        "怎么办",
        "要不要",
    )
    _skeptic_markers = (
        "risk",
        "risks",
        "risky",
        "blind spot",
        "blind spots",
        "failure mode",
        "counterexample",
        "counter-example",
        "risky",
        "风险",
        "漏洞",
        "反例",
        "质疑",
        "坏处",
        "隐患",
    )
    _builder_markers = (
        "plan",
        "roadmap",
        "implement",
        "implementation",
        "build",
        "steps",
        "milestone",
        "execution",
        "计划",
        "路线图",
        "实现",
        "步骤",
        "里程碑",
        "执行",
        "怎么做",
    )

    def decide(self, persona_input: PersonaInput) -> PersonaActivation:
        text = persona_input.user_message.strip()
        normalized = text.lower()
        if any(marker in normalized for marker in self._explicit_markers):
            return PersonaActivation(
                trigger="explicit_request",
                selected_personas=(ANALYST_PERSONA, SKEPTIC_PERSONA),
            )
        if any(marker in normalized for marker in self._skeptic_markers):
            return PersonaActivation(trigger="skeptic_heuristic", selected_personas=(SKEPTIC_PERSONA,))
        if any(marker in normalized for marker in self._builder_markers):
            return PersonaActivation(trigger="builder_heuristic", selected_personas=(BUILDER_PERSONA,))
        if any(marker in normalized for marker in self._depth_markers):
            return PersonaActivation(trigger="depth_heuristic", selected_personas=(ANALYST_PERSONA,))
        if len(text) >= 180 and ("?" in text or "？" in text):
            return PersonaActivation(trigger="depth_heuristic", selected_personas=(ANALYST_PERSONA,))
        return PersonaActivation(trigger="not_needed")


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

SKEPTIC_PERSONA = PersonaDefinition(
    id="skeptic_self",
    description="Challenges assumptions, risks, and missing counter-evidence.",
)

BUILDER_PERSONA = PersonaDefinition(
    id="builder_self",
    description="Turns intent into practical steps, milestones, and execution order.",
)
