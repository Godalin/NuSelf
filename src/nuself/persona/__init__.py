"""Persona subsystem — definitions, graph, competitive discussion, and dynamic prompts."""

from nuself.persona.definition import (
    BUILTIN_PERSONAS,
    MODERATOR_PERSONA,
    PersonaActivation,
    PersonaContribution,
    PersonaDefinition,
    PersonaInput,
    PersonaTurnState,
)
from nuself.persona.graph import (
    AgentBackedActivationPolicy,
    AgentBackedPersonaNode,
    AgentBackedSynthesizerNode,
    PersonaGraphAgents,
    PersonaGraphDriver,
    persona_graph_agents,
)
from nuself.persona.discussion import (
    AgentBackedScoringPersonaNode,
    PersonaCompetitionResult,
    PersonaDiscussionAgents,
    ProactivePersonaDiscussion,
    SharedPersonaDiscussionService,
)

__all__ = [
    "BUILTIN_PERSONAS",
    "AgentBackedScoringPersonaNode",
    "AgentBackedActivationPolicy",
    "AgentBackedPersonaNode",
    "AgentBackedSynthesizerNode",
    "MODERATOR_PERSONA",
    "PersonaActivation",
    "PersonaCompetitionResult",
    "PersonaContribution",
    "PersonaDefinition",
    "PersonaDiscussionAgents",
    "PersonaGraphDriver",
    "PersonaGraphAgents",
    "PersonaInput",
    "PersonaTurnState",
    "ProactivePersonaDiscussion",
    "SharedPersonaDiscussionService",
    "persona_graph_agents",
]
