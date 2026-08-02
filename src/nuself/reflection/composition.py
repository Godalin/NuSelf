"""Reflection-owned orchestration composition."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.config import ReflectionSettings, RuntimePaths
from nuself.conversation import ConversationHistoryService
from nuself.llm import LangChainLLMEndpoint
from nuself.memory.composition import MemoryRepositories
from nuself.notification.outbox import NotificationOutbox
from nuself.reflection.candidates import IdeaCandidateGenerator
from nuself.reflection.relevance import LLMRelevanceGate
from nuself.reflection.scheduler import ReflectionScheduler
from nuself.reflection.repository import ReflectionRepository
from nuself.reflection.service import ReflectionService
from nuself.reflection.organizer import ReflectionOrganizer
from nuself.persona.discussion import SharedPersonaDiscussionService
from nuself.reason.service import ReasonService
from nuself.storage import StorageBackend
from nuself.trace.service import TraceRecorder


@dataclass(frozen=True)
class ReflectionResources:
    """Reflection capabilities sharing one repository identity."""

    repository: ReflectionRepository
    service: ReflectionService


def compose_reflection_resources(
    paths: RuntimePaths,
    backend: StorageBackend,
    reason_service: ReasonService,
    trace_recorder: TraceRecorder,
) -> ReflectionResources:
    """Compose Reflection's authority-scoped capabilities."""

    repository = ReflectionRepository(paths, backend=backend)
    return ReflectionResources(
        repository=repository,
        service=ReflectionService(
            repository,
            reason_service,
            trace_recorder,
            ReflectionOrganizer(
                paths.authority_root,
                repository=repository,
            ),
        ),
    )


def compose_reflection_scheduler(
    paths: RuntimePaths,
    memory: MemoryRepositories,
    conversation_history: ConversationHistoryService,
    repository: ReflectionRepository,
    service: ReflectionService,
    notifications: NotificationOutbox,
    trace_recorder: TraceRecorder,
    *,
    config: ReflectionSettings,
    language_preference: str,
    langchain_models: tuple[LangChainLLMEndpoint, ...],
) -> ReflectionScheduler:
    """Compose reflection orchestration from one authority-owned graph."""

    generator = IdeaCandidateGenerator(
        paths.authority_root,
        memory_repository=memory.entries,
        source_repository=memory.sources,
        profile_repository=memory.profile,
        conversation_history=conversation_history,
        language_preference=language_preference,
        langchain_models=langchain_models,
    )
    gate = LLMRelevanceGate(
        paths.authority_root,
        config,
        repository=repository,
        langchain_models=langchain_models,
    )
    return ReflectionScheduler(
        paths.authority_root,
        config,
        repository=repository,
        outbox=notifications,
        trace_recorder=trace_recorder,
        candidate_generator=generator,
        relevance_gate=gate,
        organizer=service,
        discussion=SharedPersonaDiscussionService(
            project_root=paths.authority_root,
            config=config,
            language_preference=language_preference,
            langchain_models=langchain_models,
        ),
    )
