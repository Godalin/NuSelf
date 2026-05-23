"""Persona subsystem — definitions, graph, competitive discussion, and dynamic prompts."""

from nuself.persona.definition import (
    BUILTIN_PERSONAS,
    MODERATOR_PERSONA,
    PersonaActivation,
    PersonaContribution,
    PersonaDefinition,
    PersonaInput,
    PersonaTurnState,
    load_persona_definitions,
)
from nuself.persona.graph import (
    LLMBackedActivationPolicy,
    LLMBackedPersonaNode,
    LLMBackedSynthesizerNode,
    PersonaGraphDriver,
)
from nuself.persona.discussion import (
    PersonaCompetitionResult,
    ProactivePersonaDiscussion,
    SharedPersonaDiscussionService,
)
from nuself.persona.prompt_repo import PersonaPrompt, PersonaPromptRepository
from nuself.persona.tools import build_persona_tools

__all__ = [
    "BUILTIN_PERSONAS",
    "LLMBackedActivationPolicy",
    "LLMBackedPersonaNode",
    "LLMBackedSynthesizerNode",
    "MODERATOR_PERSONA",
    "PersonaActivation",
    "PersonaCompetitionResult",
    "PersonaContribution",
    "PersonaDefinition",
    "PersonaGraphDriver",
    "PersonaInput",
    "PersonaPrompt",
    "PersonaPromptRepository",
    "PersonaTurnState",
    "ProactivePersonaDiscussion",
    "SharedPersonaDiscussionService",
    "build_persona_tools",
    "load_persona_definitions",
]
