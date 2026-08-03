"""Reflection-owned orchestration composition."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.config.settings import ReflectionSettings, RuntimePaths
from nuself.conversation import ConversationHistoryService
from nuself.agent.endpoint import LangChainLLMEndpoint
from nuself.memory.composition import MemoryRepositories
from nuself.delivery.store import DeliveryStore
from nuself.inbox.service import InboxService
from nuself.reflection.candidates import IdeaCandidateGenerator
from nuself.reflection.relevance import LLMRelevanceGate
from nuself.reflection.scheduler import ReflectionScheduler
from nuself.reflection.repository import ReflectionRepository
from nuself.reflection.service import ReflectionService
from nuself.reflection.organizer import ReflectionOrganizer
from nuself.persona.discussion import SharedPersonaDiscussionService
from nuself.reason.service import ReasonService
from nuself.storage.contract import StorageBackend
from nuself.trace.service import TraceRecorder
from nuself.source.service import SourceService


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
    sources: SourceService,
    conversation_history: ConversationHistoryService,
    repository: ReflectionRepository,
    service: ReflectionService,
    inbox: InboxService,
    deliveries: DeliveryStore,
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
        source_service=sources,
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
        inbox=inbox,
        deliveries=deliveries,
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
