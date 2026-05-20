"""Minimal internal persona graph skeleton."""

from __future__ import annotations

import json

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Protocol, TypeVar, TypedDict, cast

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph  # type: ignore[reportMissingTypeStubs]
from pydantic import BaseModel, Field, ValidationError

from nuself.llm_json import parse_llm_json_object
from nuself.llm import (
    ChatLLM,
    ChatMessage,
    LangChainLLMEndpoint,
    is_endpoint_availability_error,
    record_llm_endpoint_success,
)

StructuredPersonaT = TypeVar("StructuredPersonaT", bound=BaseModel)


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
    should_escalate: bool = False
    escalation_reason: str = ""

    @property
    def activated(self) -> bool:
        return bool(self.selected_personas)


class PersonaContributionOutput(BaseModel):
    """Structured persona note returned by a LangChain model."""

    note: str = Field(description="One or two sentences from the persona perspective.")
    questions: list[str] = Field(default_factory=list, description="Optional questions this persona would ask.")
    confidence: float | None = Field(default=None, description="Optional confidence from 0.0 to 1.0.")


class PersonaSynthesisOutput(BaseModel):
    """Structured persona synthesis returned by a LangChain model."""

    summary: str = Field(description="One or two crisp sentences capturing consensus or key tension.")
    confidence: float | None = Field(default=None, description="Optional confidence from 0.0 to 1.0.")


class PersonaActivationOutput(BaseModel):
    """Structured persona activation decision returned by a LangChain model."""

    activated: bool = Field(description="Whether any personas should respond.")
    selected_persona_ids: list[str] = Field(default_factory=list, description="Persona ids to activate.")
    trigger: str = Field(default="structured judgment", description="Brief reason for activation.")
    should_escalate: bool = Field(default=False, description="Whether competitive discussion should run.")
    escalation_reason: str = Field(default="", description="Brief reason for escalation.")


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
            remaining = endpoints[position + 1 :]
            if remaining and is_endpoint_availability_error(str(exc)):
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
        except Exception:
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
        except Exception:
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
            # No LLM available → safe fallback: no activation, no escalation
            return PersonaActivation(trigger="no_llm")
        try:
            return self._decide_with_llm(persona_input)
        except (RuntimeError, ValueError, KeyError) as e:
            return PersonaActivation(
                trigger="llm_fallback",
                selected_personas=(),
                should_escalate=False,
                escalation_reason=f"fallback: {e}",
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

        try:
            output = PersonaActivationOutput.model_validate_json(stripped)
            return self._activation_from_structured(output)
        except (ValidationError, json.JSONDecodeError):
            pass

        data = parse_llm_json_object(raw)

        activated = data.get("activated")
        if isinstance(activated, bool):
            pass
        elif isinstance(activated, str):
            activated = activated.lower() in {"true", "yes", "1"}
        else:
            activated = False

        selected_ids = data.get("selected_persona_ids")
        selected: list[PersonaDefinition] = []
        if isinstance(selected_ids, list):
            for pid in cast(list[object], selected_ids):
                if isinstance(pid, str) and pid in self._persona_by_id:
                    selected.append(self._persona_by_id[pid])

        trigger = data.get("trigger")
        if not isinstance(trigger, str):
            trigger = "llm judgment"

        should_escalate = data.get("should_escalate")
        if isinstance(should_escalate, bool):
            pass
        elif isinstance(should_escalate, str):
            should_escalate = should_escalate.lower() in {"true", "yes", "1"}
        else:
            should_escalate = False

        escalation_reason = data.get("escalation_reason")
        if not isinstance(escalation_reason, str):
            escalation_reason = ""

        return PersonaActivation(
            trigger=trigger,
            selected_personas=tuple(selected),
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
        )


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

MODERATOR_PERSONA = PersonaDefinition(
    id="moderator_self",
    description="Keeps persona discussion converging and invites silence when a turn adds nothing new.",
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
