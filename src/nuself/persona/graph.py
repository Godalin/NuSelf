"""Persona graph nodes, driver, and helpers."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, TypeVar, TypedDict, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph  # type: ignore[reportMissingTypeStubs]
from pydantic import BaseModel

from nuself.llm import (
    ChatLLM,
    ChatMessage,
    LangChainLLMEndpoint,
    is_endpoint_availability_error,
    record_llm_endpoint_success,
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
from nuself.runtime.observability import report_observed_failure

StructuredPersonaT = TypeVar("StructuredPersonaT", bound=BaseModel)


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


def _complete_persona_structured(
    endpoints: tuple[LangChainLLMEndpoint, ...],
    messages: list[ChatMessage],
    schema: type[StructuredPersonaT],
    *,
    project_root: Path | None,
) -> StructuredPersonaT | None:
    if not endpoints:
        return None
    converted = _to_langchain_messages(messages)
    for position, endpoint in enumerate(endpoints):
        try:
            structured_model = endpoint.model.with_structured_output(schema)
            result = structured_model.invoke(converted)
            if isinstance(result, schema):
                record_llm_endpoint_success(project_root, endpoint.index)
                return result
            if isinstance(result, dict):
                record_llm_endpoint_success(project_root, endpoint.index)
                return schema.model_validate(result)
            raise TypeError(f"structured persona output must be {schema.__name__}")
        except Exception as exc:
            # Fail visible: log every endpoint failure (including schema/validation
            # errors) instead of silently returning None, and fail over to the next
            # endpoint on any error, matching the chat runtime's failover policy.
            report_observed_failure(
                exc,
                component="persona",
                event="persona_structured_failed",
                message=(
                    "structured persona output failed on endpoint "
                    f"{endpoint.index} ({schema.__name__})"
                ),
                project_root=project_root,
                level="warning",
                status="error",
                metadata={
                    "endpoint": endpoint.index,
                    "availability": is_endpoint_availability_error(str(exc)),
                    "schema": schema.__name__,
                },
            )
            if position + 1 < len(endpoints):
                continue
            return None
    return None


def _to_langchain_messages(messages: list[ChatMessage]) -> list[BaseMessage]:
    converted: list[BaseMessage] = []
    for message in messages:
        if message.role == "system":
            converted.append(SystemMessage(content=message.content))
        else:
            converted.append(HumanMessage(content=message.content))
    return converted


class LLMBackedPersonaNode:
    """LLM-driven persona node that generates genuinely distinct perspectives."""

    def __init__(
        self,
        llm: ChatLLM,
        *,
        language_preference: str = "en",
        langchain_models: tuple[LangChainLLMEndpoint, ...] = (),
        project_root: Path | None = None,
    ) -> None:
        self._llm = llm
        self._language_preference = language_preference
        self._langchain_models = langchain_models
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
            ChatMessage(
                role="system",
                content=(
                    f"You are {persona.id} in a private reflection council. "
                    f"Your role: {persona.description}\n"
                    "Respond in 1-2 sentences from your unique perspective. "
                    "Do not repeat what others said. If others have spoken, build on or challenge their points."
                    f"{response_language}"
                ),
            ),
            ChatMessage(
                role="user",
                content=f"Topic:\n{persona_input.user_message}{prior_block}",
            ),
        ]
        structured = _complete_persona_structured(
            self._langchain_models,
            messages,
            PersonaContributionOutput,
            project_root=self._project_root,
        )
        if structured is not None:
            return PersonaContribution(
                persona_id=persona.id,
                notes=(structured.note,),
                questions=tuple(structured.questions),
                confidence=structured.confidence,
            )
        try:
            response = self._llm.complete(messages).strip()
        except Exception as exc:
            report_observed_failure(
                exc,
                component="persona",
                event="persona_completion_failed",
                message=f"persona contribution fallback used for {persona.id}",
                project_root=self._project_root,
                metadata={
                    "stage": "contribution",
                    "persona_id": persona.id,
                },
            )
            response = f"{persona.id} considered the topic."

        return PersonaContribution(persona_id=persona.id, notes=(response,), confidence=0.5)


class LLMBackedSynthesizerNode:
    """LLM-driven synthesizer that produces a crisp summary of contributions."""

    def __init__(
        self,
        llm: ChatLLM,
        *,
        language_preference: str = "en",
        langchain_models: tuple[LangChainLLMEndpoint, ...] = (),
        project_root: Path | None = None,
    ) -> None:
        self._llm = llm
        self._language_preference = language_preference
        self._langchain_models = langchain_models
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
            ChatMessage(
                role="system",
                content=(
                    "You are the synthesizer. Distill the discussion into 1-2 crisp sentences "
                    f"that capture the consensus or key tension.{response_language}"
                ),
            ),
            ChatMessage(role="user", content=discussion),
        ]
        structured = _complete_persona_structured(
            self._langchain_models,
            messages,
            PersonaSynthesisOutput,
            project_root=self._project_root,
        )
        if structured is not None:
            return PersonaSynthesis(
                summary=structured.summary,
                source_personas=tuple(c.persona_id for c in turn_state.contributions),
                confidence=structured.confidence,
            )
        try:
            summary = self._llm.complete(messages).strip()
        except Exception as exc:
            report_observed_failure(
                exc,
                component="persona",
                event="persona_completion_failed",
                message="persona synthesis fallback used",
                project_root=self._project_root,
                metadata={"stage": "synthesis"},
            )
            summary = " | ".join(lines)
        return PersonaSynthesis(
            summary=summary,
            source_personas=tuple(c.persona_id for c in turn_state.contributions),
            confidence=0.5,
        )


class LLMBackedActivationPolicy:
    """LLM-driven policy that decides which personas to activate and whether to escalate."""

    def __init__(
        self,
        personas: tuple[PersonaDefinition, ...] | None = None,
        llm: ChatLLM | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] = (),
        project_root: Path | None = None,
    ) -> None:
        self._personas = personas if personas is not None else BUILTIN_PERSONAS
        self._persona_by_id = {p.id: p for p in self._personas}
        self._llm = llm
        self._langchain_models = langchain_models
        self._project_root = project_root

    def decide(self, persona_input: PersonaInput) -> PersonaActivation:
        if self._llm is None:
            return PersonaActivation(trigger="no_llm")
        try:
            return self._decide_with_llm(persona_input)
        except (RuntimeError, ValueError, KeyError) as exc:
            report_observed_failure(
                exc,
                component="persona",
                event="persona_activation_failed",
                message="persona activation fallback used",
                project_root=self._project_root,
                metadata={"stage": "activation"},
            )
            return PersonaActivation(
                trigger="llm_fallback",
                selected_personas=(),
                should_escalate=False,
                escalation_reason=f"fallback: {exc}",
            )

    def _decide_with_llm(self, persona_input: PersonaInput) -> PersonaActivation:
        assert self._llm is not None
        messages = self._build_prompt(persona_input)
        structured = _complete_persona_structured(
            self._langchain_models,
            messages,
            PersonaActivationOutput,
            project_root=self._project_root,
        )
        if structured is not None:
            return self._activation_from_structured(structured)
        raw = self._llm.complete(messages)
        return self._parse_response(raw)

    def _activation_from_structured(self, output: PersonaActivationOutput) -> PersonaActivation:
        selected = tuple(self._persona_by_id[pid] for pid in output.selected_persona_ids if pid in self._persona_by_id)
        return PersonaActivation(
            trigger=output.trigger,
            selected_personas=selected if output.activated else (),
            should_escalate=output.should_escalate,
            escalation_reason=output.escalation_reason,
        )

    def _build_prompt(self, persona_input: PersonaInput) -> list[ChatMessage]:
        from nuself.llm import ChatMessage

        system = (
            "You are the Persona Activation Gate for NuSelf, a private AI mirror. "
            "Your job is to decide which internal thought selves (personas) should "
            "respond to the user's message, and whether the topic warrants a "
            "competitive multi-persona discussion.\n\n"
            "Return ONLY a JSON object with these fields:\n"
            "- activated (bool): Should any personas respond?\n"
            "- selected_persona_ids (list of strings): Which personas are relevant? Empty if none.\n"
            "- trigger (string): Brief reason for the selection.\n"
            "- should_escalate (bool): Should this enter competitive multi-persona discussion?\n"
            "- escalation_reason (string): Brief reason for escalation.\n\n"
            "No markdown fences."
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
            ChatMessage(role="system", content=system),
            ChatMessage(role="user", content="\n".join(lines)),
        ]

    def _parse_response(self, raw: str) -> PersonaActivation:
        stripped = raw.strip()
        if stripped.startswith("```"):
            lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
            stripped = "\n".join(lines).strip()

        output = PersonaActivationOutput.model_validate_json(stripped)
        return self._activation_from_structured(output)


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
