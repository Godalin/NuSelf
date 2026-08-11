"""Reflection-owned orchestration composition."""

from __future__ import annotations

from nuself.config.settings import ReflectionSettings, RuntimePaths
from nuself.conversation import ConversationHistoryService
from nuself.agent.endpoint import LangChainLLMEndpoint
from nuself.memory.service import MemoryService
from nuself.profile.service import ProfileService
from nuself.delivery.service import DeliveryService
from nuself.inbox.service import InboxService
from nuself.reflection.candidates import IdeaCandidateGenerator
from nuself.reflection.relevance import LLMRelevanceGate
from nuself.reflection.rendering import LLMChineseTranslator, ProvenanceRenderer
from nuself.reflection.scheduler import ReflectionScheduler
from nuself.reflection.repository import ReflectionRepository
from nuself.reflection.service import ReflectionService
from nuself.reflection.organizer import ReflectionOrganizer
from nuself.persona.discussion import SharedPersonaDiscussionService
from nuself.reason.service import ReasonService
from nuself.storage.contract import StorageBackend
from nuself.trace.service import TraceRecorder
from nuself.trace.provenance import ProvenanceService
from nuself.source.service import SourceService


def compose_reflection_service(
    paths: RuntimePaths,
    backend: StorageBackend,
    reason_service: ReasonService,
    trace_recorder: TraceRecorder,
) -> ReflectionService:
    """Compose Reflection's authority-scoped service."""

    repository = ReflectionRepository(paths, backend=backend)
    return ReflectionService(
        repository,
        reason_service,
        trace_recorder,
        ReflectionOrganizer(
            paths.authority_root,
            repository=repository,
        ),
    )


def compose_reflection_scheduler(
    paths: RuntimePaths,
    memory: MemoryService,
    profiles: ProfileService,
    sources: SourceService,
    conversation_history: ConversationHistoryService,
    service: ReflectionService,
    inbox: InboxService,
    deliveries: DeliveryService,
    trace_recorder: TraceRecorder,
    provenance: ProvenanceService,
    *,
    config: ReflectionSettings,
    language_preference: str,
    langchain_models: tuple[LangChainLLMEndpoint, ...],
) -> ReflectionScheduler:
    """Compose reflection orchestration from one authority-owned graph."""

    generator = IdeaCandidateGenerator(
        paths.authority_root,
        memory_service=memory,
        source_service=sources,
        profile_service=profiles,
        conversation_history=conversation_history,
        language_preference=language_preference,
        langchain_models=langchain_models,
    )
    gate = LLMRelevanceGate(
        paths.authority_root,
        config,
        service=service,
        langchain_models=langchain_models,
    )
    return ReflectionScheduler(
        paths.authority_root,
        config,
        service=service,
        inbox=inbox,
        deliveries=deliveries,
        trace_recorder=trace_recorder,
        provenance=provenance,
        provenance_renderer=ProvenanceRenderer(
            LLMChineseTranslator(
                paths.authority_root,
                langchain_models=langchain_models,
            )
        ),
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
