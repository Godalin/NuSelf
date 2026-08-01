"""Persona data model layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Protocol, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

NonBlankText: TypeAlias = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


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

    model_config = ConfigDict(strict=True, extra="forbid")

    note: NonBlankText = Field(
        description="One or two sentences from the persona perspective.",
    )
    questions: list[NonBlankText] = Field(
        max_length=3,
        description="Questions this persona would ask, possibly empty.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence from 0.0 to 1.0.",
    )


class PersonaSynthesisOutput(BaseModel):
    """Structured persona synthesis returned by a LangChain model."""

    model_config = ConfigDict(strict=True, extra="forbid")

    summary: NonBlankText = Field(
        description="One or two crisp sentences capturing consensus or key tension.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence from 0.0 to 1.0.",
    )


class PersonaActivationOutput(BaseModel):
    """Structured persona activation decision returned by a LangChain model."""

    model_config = ConfigDict(strict=True, extra="forbid")

    activated: bool = Field(description="Whether any personas should respond.")
    selected_persona_ids: list[NonBlankText] = Field(
        max_length=5,
        description="Persona ids to activate.",
    )
    trigger: NonBlankText = Field(description="Brief reason for activation.")
    should_escalate: bool = Field(
        description="Whether competitive discussion should run."
    )
    escalation_reason: NonBlankText = Field(
        description="Brief reason for escalation decision."
    )

    @model_validator(mode="after")
    def _activation_state_is_consistent(self) -> PersonaActivationOutput:
        if self.activated != bool(self.selected_persona_ids):
            raise ValueError(
                "activated must match whether persona ids are selected"
            )
        if self.should_escalate and not self.activated:
            raise ValueError(
                "escalation requires an activated persona selection"
            )
        return self


@dataclass(frozen=True)
class PersonaTurnState:
    """State passed through the minimal persona graph."""

    input: PersonaInput
    selected_personas: tuple[PersonaDefinition, ...]
    contributions: tuple[PersonaContribution, ...] = ()
    synthesis: PersonaSynthesis | None = None
    node_trace: tuple[str, ...] = ()


class PersonaNode(Protocol):
    """Callable shape for one persona node."""

    def __call__(self, persona: PersonaDefinition, persona_input: PersonaInput) -> PersonaContribution: ...


class PersonaSynthesizerNode(Protocol):
    """Callable shape for synthesis from persona contributions."""

    def __call__(self, turn_state: PersonaTurnState) -> PersonaSynthesis | None: ...


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
