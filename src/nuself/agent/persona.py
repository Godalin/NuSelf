"""Minimal internal persona graph skeleton."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
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
class PersonaSynthesis:
    """Compact internal synthesis over persona contributions."""

    summary: str
    source_personas: tuple[str, ...] = ()
    confidence: float | None = None
    answer: str | None = None
    evidence_references: tuple[str, ...] = ()
    epistemic_status: str | None = None


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
    synthesis: PersonaSynthesis | None = None
    node_trace: tuple[str, ...] = ()


class PersonaGraphState(TypedDict):
    """LangGraph state wrapper for a persona turn."""

    turn_state: PersonaTurnState


class PersonaNode(Protocol):
    """Callable shape for one persona node."""

    def __call__(self, persona: PersonaDefinition, persona_input: PersonaInput) -> PersonaContribution: ...


class PersonaSynthesizerNode(Protocol):
    """Callable shape for synthesis from persona contributions."""

    def __call__(self, turn_state: PersonaTurnState) -> PersonaSynthesis | None: ...


class MinimalPersonaNode:
    """Deterministic placeholder persona node used before LLM-backed personas."""

    def __call__(self, persona: PersonaDefinition, persona_input: PersonaInput) -> PersonaContribution:
        memory_context = persona_input.memory_context.strip()
        if memory_context:
            context_note = f" after hearing: {_compact_text(memory_context, 140)}"
        else:
            context_note = ""
        if persona.id == "skeptic_self":
            note = f"{persona.id} challenged assumptions in: {persona_input.user_message}{context_note}"
            return PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0)
        if persona.id == "builder_self":
            note = f"{persona.id} proposed concrete steps for: {persona_input.user_message}{context_note}"
            return PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0)
        if persona.id == "historian_self":
            note = f"{persona.id} connected prior context to: {persona_input.user_message}{context_note}"
            return PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0)
        if persona.id == "care_self":
            note = f"{persona.id} highlighted emotional and human impact in: {persona_input.user_message}{context_note}"
            return PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0)
        note = f"{persona.id} considered: {persona_input.user_message}{context_note}"
        return PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0)


def _compact_text(text: str, limit: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."


class MinimalSynthesizerNode:
    """Deterministic synthesis over persona contributions."""

    def __call__(self, turn_state: PersonaTurnState) -> PersonaSynthesis | None:
        if not turn_state.contributions:
            return None
        persona_ids = tuple(contrib.persona_id for contrib in turn_state.contributions)
        top_notes: list[str] = []
        for contrib in turn_state.contributions:
            if contrib.notes:
                top_notes.append(contrib.notes[0])
        if not top_notes:
            summary = "; ".join(persona_ids)
        else:
            summary = " | ".join(top_notes)
        return PersonaSynthesis(
            summary=summary,
            source_personas=persona_ids,
            confidence=0.0,
        )


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
    _historian_markers = (
        "history",
        "historical",
        "timeline",
        "earlier",
        "previously",
        "before",
        "past",
        "回顾",
        "之前",
        "过去",
        "时间线",
        "复盘",
    )
    _care_markers = (
        "feel",
        "feeling",
        "emotion",
        "emotional",
        "stress",
        "burnout",
        "support",
        "care",
        "担心",
        "焦虑",
        "情绪",
        "压力",
        "照顾",
        "支持",
        "共情",
    )

    def __init__(self, personas: tuple[PersonaDefinition, ...] | None = None) -> None:
        self._personas = personas if personas is not None else BUILTIN_PERSONAS
        self._persona_by_id = {p.id: p for p in self._personas}

    def _maybe(self, persona_id: str) -> PersonaDefinition | None:
        return self._persona_by_id.get(persona_id)

    def decide(self, persona_input: PersonaInput) -> PersonaActivation:
        text = persona_input.user_message.strip()
        normalized = text.lower()
        has_skeptic = any(marker in normalized for marker in self._skeptic_markers)
        has_builder = any(marker in normalized for marker in self._builder_markers)
        has_depth = any(marker in normalized for marker in self._depth_markers) or (
            len(text) >= 180 and ("?" in text or "？" in text)
        )
        has_historian = any(marker in normalized for marker in self._historian_markers)
        has_care = any(marker in normalized for marker in self._care_markers)

        selected_by_relevance: list[PersonaDefinition] = []
        skeptic = self._maybe("skeptic_self")
        builder = self._maybe("builder_self")
        analyst = self._maybe("analyst_self")
        historian = self._maybe("historian_self")
        care = self._maybe("care_self")

        if has_skeptic and skeptic is not None:
            selected_by_relevance.append(skeptic)
        if has_builder and builder is not None:
            selected_by_relevance.append(builder)
        if has_depth and analyst is not None:
            selected_by_relevance.append(analyst)
        if has_historian and historian is not None:
            selected_by_relevance.append(historian)
        if has_care and care is not None:
            selected_by_relevance.append(care)

        if any(marker in normalized for marker in self._explicit_markers):
            if selected_by_relevance:
                return PersonaActivation(trigger="explicit_relevant_personas", selected_personas=tuple(selected_by_relevance))
            fallback: list[PersonaDefinition] = []
            if analyst is not None:
                fallback.append(analyst)
            if skeptic is not None:
                fallback.append(skeptic)
            if fallback:
                return PersonaActivation(trigger="explicit_request", selected_personas=tuple(fallback))
            return PersonaActivation(trigger="not_needed")

        if len(selected_by_relevance) >= 2:
            return PersonaActivation(trigger="mixed_intent_heuristic", selected_personas=tuple(selected_by_relevance))

        if has_skeptic and skeptic is not None:
            return PersonaActivation(trigger="skeptic_heuristic", selected_personas=(skeptic,))
        if has_builder and builder is not None:
            return PersonaActivation(trigger="builder_heuristic", selected_personas=(builder,))
        if has_depth and analyst is not None:
            return PersonaActivation(trigger="depth_heuristic", selected_personas=(analyst,))
        if has_historian and historian is not None:
            return PersonaActivation(trigger="historian_heuristic", selected_personas=(historian,))
        if has_care and care is not None:
            return PersonaActivation(trigger="care_heuristic", selected_personas=(care,))
        return PersonaActivation(trigger="not_needed")


class PersonaGraphDriver:
    """Minimal LangGraph-backed persona subgraph."""

    def __init__(
        self,
        *,
        persona_node: PersonaNode | None = None,
        synthesizer_node: PersonaSynthesizerNode | None = None,
    ) -> None:
        self._persona_node = persona_node or MinimalPersonaNode()
        self._synthesizer_node = synthesizer_node or MinimalSynthesizerNode()
        graph: Any = StateGraph(PersonaGraphState)
        graph.add_node("run_personas", self._run_personas)
        graph.add_node("run_synthesizer", self._run_synthesizer)
        graph.add_edge(START, "run_personas")
        graph.add_edge("run_personas", "run_synthesizer")
        graph.add_edge("run_synthesizer", END)
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

    def _run_synthesizer(self, state: PersonaGraphState) -> PersonaGraphState:
        turn_state = state["turn_state"]
        synthesis = self._synthesizer_node(turn_state)
        return {
            "turn_state": replace(
                turn_state,
                synthesis=synthesis,
                node_trace=(*turn_state.node_trace, "run_synthesizer"),
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

HISTORIAN_PERSONA = PersonaDefinition(
    id="historian_self",
    description="Connects prior context and timelines to current decisions.",
)

CARE_PERSONA = PersonaDefinition(
    id="care_self",
    description="Highlights emotional impact, support, and sustainable pacing.",
)

SYNTHESIZER_PERSONA = PersonaDefinition(
    id="synthesizer_self",
    description="Fuses persona contributions into compact internal synthesis.",
)

BUILTIN_PERSONAS = (
    ANALYST_PERSONA,
    SKEPTIC_PERSONA,
    BUILDER_PERSONA,
    HISTORIAN_PERSONA,
    CARE_PERSONA,
)


def load_persona_definitions(project_root: Path | None = None) -> tuple[PersonaDefinition, ...]:
    """Load persona definitions from durable memory entries.

    Falls back to built-in personas when no durable instructions exist.
    """
    from nuself.memory.repository import MemoryEntryRepository, MemorySearchFilters

    try:
        repo = MemoryEntryRepository(project_root)
        entries = repo.search("", filters=MemorySearchFilters(type="persona_instruction"))
    except RuntimeError:
        return BUILTIN_PERSONAS

    definitions: list[PersonaDefinition] = []
    for entry in entries:
        memory = entry.to_memory_object()
        persona_id = memory.payload.get("persona_id")
        description = memory.payload.get("description")
        if isinstance(persona_id, str) and isinstance(description, str):
            definitions.append(PersonaDefinition(id=persona_id, description=description))

    if not definitions:
        return BUILTIN_PERSONAS
    return tuple(definitions)
