"""Application-owned composition for the reflection domain."""

from __future__ import annotations

from typing import TYPE_CHECKING
from nuself.config import ReflectionSettings
from nuself.llm import LangChainLLMEndpoint
from nuself.reflection.candidates import IdeaCandidateGenerator
from nuself.reflection.relevance import LLMRelevanceGate
from nuself.reflection.scheduler import ReflectionScheduler
from nuself.persona.discussion import SharedPersonaDiscussionService

if TYPE_CHECKING:
    from nuself.application.composition import ApplicationGraph


def compose_reflection_scheduler(
    application: "ApplicationGraph",
    *,
    config: ReflectionSettings,
    language_preference: str,
    langchain_models: tuple[LangChainLLMEndpoint, ...],
) -> ReflectionScheduler:
    """Compose reflection orchestration from one authority-owned graph."""

    paths = application.paths
    generator = IdeaCandidateGenerator(
        paths.project_root,
        config=config,
        memory_repository=application.memory.entries,
        source_repository=application.memory.sources,
        profile_repository=application.memory.profile,
        conversation_history=application.conversation_history,
        language_preference=language_preference,
        langchain_models=langchain_models,
    )
    gate = LLMRelevanceGate(
        paths.project_root,
        config,
        repository=application.reflection,
        langchain_models=langchain_models,
    )
    return ReflectionScheduler(
        paths.project_root,
        config,
        repository=application.reflection,
        outbox=application.notifications,
        trace_recorder=application.trace.recorder,
        candidate_generator=generator,
        relevance_gate=gate,
        organizer=application.reflection_service,
        discussion=SharedPersonaDiscussionService(
            project_root=paths.project_root,
            config=config,
            language_preference=language_preference,
            langchain_models=langchain_models,
        ),
    )
