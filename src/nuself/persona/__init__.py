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
    AgentBackedScoringPersonaNode,
    PersonaCompetitionResult,
    PersonaDiscussionAgents,
    ProactivePersonaDiscussion,
    SharedPersonaDiscussionService,
    default_persona_discussion_agents,
)
from nuself.persona.prompt_repo import PersonaPrompt, PersonaPromptRepository
from nuself.persona.tools import build_persona_tools

__all__ = [
    "BUILTIN_PERSONAS",
    "AgentBackedScoringPersonaNode",
    "LLMBackedActivationPolicy",
    "LLMBackedPersonaNode",
    "LLMBackedSynthesizerNode",
    "MODERATOR_PERSONA",
    "PersonaActivation",
    "PersonaCompetitionResult",
    "PersonaContribution",
    "PersonaDefinition",
    "PersonaDiscussionAgents",
    "PersonaGraphDriver",
    "PersonaInput",
    "PersonaPrompt",
    "PersonaPromptRepository",
    "PersonaTurnState",
    "ProactivePersonaDiscussion",
    "SharedPersonaDiscussionService",
    "build_persona_tools",
    "default_persona_discussion_agents",
    "load_persona_definitions",
]
