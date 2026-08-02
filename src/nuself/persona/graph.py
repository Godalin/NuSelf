"""Persona graph nodes, driver, and helpers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, TypedDict, cast

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph  # type: ignore[reportMissingTypeStubs]

from nuself.agent.failover import is_recoverable_agent_failure
from nuself.agent.structured import (
    LangChainStructuredAgent,
    StructuredAgent,
)
from nuself.llm import (
    LangChainLLMEndpoint,
)
from nuself.persona.definition import (
    BUILTIN_PERSONAS,
    PersonaActivation,
    PersonaActivationOutput,
    PersonaContribution,
    PersonaContributionOutput,
    PersonaDefinition,
    PersonaInput,
    PersonaNode,
    PersonaSynthesis,
    PersonaSynthesisOutput,
    PersonaSynthesizerNode,
    PersonaTurnState,
)
from nuself.runtime.diagnostics import diagnostic_exception_message
from nuself.persona.audit import PERSONA_AUDIT

class PersonaGraphState(TypedDict):
    """LangGraph state wrapper for a persona turn."""

    turn_state: PersonaTurnState


class MinimalPersonaNode:
    """Deterministic placeholder persona node used before LLM-backed personas."""

    def __call__(self, persona: PersonaDefinition, persona_input: PersonaInput) -> PersonaContribution:
        memory_context = persona_input.memory_context.strip()
        if memory_context:
            context_note = f" after hearing: {_compact_text(memory_context, 140)}"
        else:
            context_note = ""
        if persona.id == "moderator_self":
            note = f"{persona.id} asked the discussion to converge, avoid repetition, and only continue if a new point appears.{context_note}"
            return PersonaContribution(persona_id=persona.id, notes=(note,), confidence=0.0)
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


@dataclass(frozen=True)
class PersonaGraphAgents:
    """Typed agent capabilities used by the standard persona graph."""

    activation: StructuredAgent[PersonaActivationOutput]
    contribution: StructuredAgent[PersonaContributionOutput]
    synthesis: StructuredAgent[PersonaSynthesisOutput]


def persona_graph_agents(
    endpoints: tuple[LangChainLLMEndpoint, ...],
    *,
    project_root: Path | None = None,
) -> PersonaGraphAgents:
    """Compose persona graph agents from an ordered endpoint set."""
    return PersonaGraphAgents(
        activation=LangChainStructuredAgent(
            PersonaActivationOutput,
            endpoints=endpoints,
            project_root=project_root,
            component="persona",
        ),
        contribution=LangChainStructuredAgent(
            PersonaContributionOutput,
            endpoints=endpoints,
            project_root=project_root,
            component="persona",
        ),
        synthesis=LangChainStructuredAgent(
            PersonaSynthesisOutput,
            endpoints=endpoints,
            project_root=project_root,
            component="persona",
        ),
    )


class AgentBackedPersonaNode:
    """Typed-agent node that generates distinct persona perspectives."""

    def __init__(
        self,
        agent: StructuredAgent[PersonaContributionOutput],
        *,
        language_preference: str = "en",
        project_root: Path | None = None,
    ) -> None:
        self._agent = agent
        self._language_preference = language_preference
        self._project_root = project_root

    def __call__(self, persona: PersonaDefinition, persona_input: PersonaInput) -> PersonaContribution:
        prior = persona_input.memory_context.strip()
        if prior:
            prior_block = f"\nPrior discussion:\n{prior}"
        else:
            prior_block = ""

        response_language = ""
        if self._language_preference != "en":
            response_language = f" Write your response in {self._language_preference}."

        messages = [
            SystemMessage(
                content=(
                    f"You are {persona.id} in a private reflection council. "
                    f"Your role: {persona.description}\n"
                    "Respond in 1-2 sentences from your unique perspective. "
                    "Do not repeat what others said. If others have spoken, build on or challenge their points."
                    f"{response_language}"
                ),
            ),
            HumanMessage(
                content=f"Topic:\n{persona_input.user_message}{prior_block}",
            ),
        ]
        try:
            structured = self._agent.invoke(messages)
            return PersonaContribution(
                persona_id=persona.id,
                notes=(structured.note,),
                questions=tuple(structured.questions),
                confidence=structured.confidence,
            )
        except Exception as exc:
            if not is_recoverable_agent_failure(exc):
                raise
            PERSONA_AUDIT.failure(
                exc,
                event="persona_completion_failed",
                project_root=self._project_root,
                metadata={"stage": "contribution"},
            )
        return PersonaContribution(
            persona_id=persona.id,
            notes=(f"{persona.id} considered the topic.",),
            confidence=0.5,
        )


class AgentBackedSynthesizerNode:
    """Typed-agent synthesizer that produces a crisp summary."""

    def __init__(
        self,
        agent: StructuredAgent[PersonaSynthesisOutput],
        *,
        language_preference: str = "en",
        project_root: Path | None = None,
    ) -> None:
        self._agent = agent
        self._language_preference = language_preference
        self._project_root = project_root

    def __call__(self, turn_state: PersonaTurnState) -> PersonaSynthesis | None:
        if not turn_state.contributions:
            return None
        lines: list[str] = []
        for contrib in turn_state.contributions:
            note = contrib.notes[0] if contrib.notes else "(no note)"
            lines.append(f"- {contrib.persona_id}: {note}")
        discussion = "\n".join(lines)
        response_language = ""
        if self._language_preference != "en":
            response_language = f" Write the summary in {self._language_preference}."
        messages = [
            SystemMessage(
                content=(
                    "You are the synthesizer. Distill the discussion into 1-2 crisp sentences "
                    f"that capture the consensus or key tension.{response_language}"
                ),
            ),
            HumanMessage(content=discussion),
        ]
        try:
            structured = self._agent.invoke(messages)
            return PersonaSynthesis(
                summary=structured.summary,
                source_personas=tuple(c.persona_id for c in turn_state.contributions),
                confidence=structured.confidence,
            )
        except Exception as exc:
            if not is_recoverable_agent_failure(exc):
                raise
            PERSONA_AUDIT.failure(
                exc,
                event="persona_completion_failed",
                project_root=self._project_root,
                metadata={"stage": "synthesis"},
            )
        return PersonaSynthesis(
            summary=" | ".join(lines),
            source_personas=tuple(c.persona_id for c in turn_state.contributions),
            confidence=0.5,
        )


class AgentBackedActivationPolicy:
    """Typed-agent policy for persona activation and escalation."""

    def __init__(
        self,
        personas: tuple[PersonaDefinition, ...] | None = None,
        agent: StructuredAgent[PersonaActivationOutput] | None = None,
        project_root: Path | None = None,
    ) -> None:
        self._personas = personas if personas is not None else BUILTIN_PERSONAS
        self._persona_by_id = {p.id: p for p in self._personas}
        self._agent = agent
        self._project_root = project_root

    def decide(self, persona_input: PersonaInput) -> PersonaActivation:
        if self._agent is None:
            return PersonaActivation(trigger="no_agent")
        try:
            output = self._agent.invoke(self._build_prompt(persona_input))
            return self._activation_from_structured(output)
        except Exception as exc:
            if not is_recoverable_agent_failure(exc):
                raise
            PERSONA_AUDIT.failure(
                exc,
                event="persona_activation_failed",
                project_root=self._project_root,
            )
            return PersonaActivation(
                trigger="agent_fallback",
                selected_personas=(),
                should_escalate=False,
                escalation_reason=(
                    f"fallback: {diagnostic_exception_message(exc)}"
                ),
            )

    def _activation_from_structured(self, output: PersonaActivationOutput) -> PersonaActivation:
        selected = tuple(self._persona_by_id[pid] for pid in output.selected_persona_ids if pid in self._persona_by_id)
        return PersonaActivation(
            trigger=output.trigger,
            selected_personas=selected if output.activated else (),
            should_escalate=output.should_escalate,
            escalation_reason=output.escalation_reason,
        )

    def _build_prompt(
        self,
        persona_input: PersonaInput,
    ) -> list[SystemMessage | HumanMessage]:
        system = (
            "You are the Persona Activation Gate for NuSelf, a private AI mirror. "
            "Your job is to decide which internal thought selves (personas) should "
            "respond to the user's message, and whether the topic warrants a "
            "competitive multi-persona discussion. Return a complete activation "
            "decision through the required structured response."
        )

        persona_lines = [f"- {p.id}: {p.description}" for p in self._personas]

        lines: list[str] = [
            "Available personas:",
            *persona_lines,
            "",
            f"User message: {persona_input.user_message}",
        ]
        if persona_input.memory_context:
            lines.append(f"Memory context: {persona_input.memory_context}")

        return [
            SystemMessage(content=system),
            HumanMessage(content="\n".join(lines)),
        ]


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

    def run_personas_only(self, state: PersonaTurnState) -> PersonaTurnState:
        """Run only the persona node, skipping synthesis.

        For callers that need a single persona note (e.g. the moderator turn) and
        would otherwise pay for an unused synthesizer LLM call on every invocation.
        """
        graph_state = self._run_personas({"turn_state": state})
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
