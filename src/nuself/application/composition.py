"""Complete application service graph for one authority."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.memory.composition import (
    compose_memory_repositories,
    compose_memory_service,
)
from nuself.reason.composition import compose_reason_service
from nuself.application.data import DataAdminService
from nuself.application.provenance import compose_provenance_service
from nuself.trace.composition import TraceServices, compose_trace_services
from nuself.trace.provenance import ProvenanceService
from nuself.config.settings import ConfigSystem, RuntimePaths, SystemConfig
from nuself.conversation import (
    ConversationHistoryService,
    ConversationService,
    ConversationStore,
)
from nuself.delivery.store import DeliveryStore
from nuself.delivery.service import DeliveryService
from nuself.inbox.service import InboxService
from nuself.memory.service import MemoryService
from nuself.profile.service import ProfileService
from nuself.persona.prompt_repo import PersonaPromptRepository
from nuself.persona.service import PersonaService
from nuself.reflection.composition import compose_reflection_service
from nuself.reflection.service import ReflectionService
from nuself.reason.service import ReasonService
from nuself.reason.model import ReasoningStep, ReasoningThread
from nuself.application.projection import publish_reason_observation
from nuself.storage.contract import StorageBackend
from nuself.source.composition import compose_source_services
from nuself.source.importer import SourceImporter
from nuself.source.service import SourceService


@dataclass(frozen=True)
class ApplicationGraph:
    """Concrete services sharing one selected authority."""

    paths: RuntimePaths
    config: SystemConfig
    conversations: ConversationService
    conversation_history: ConversationHistoryService
    memory: MemoryService
    profiles: ProfileService
    sources: SourceService
    source_importer: SourceImporter
    inbox: InboxService
    deliveries: DeliveryService
    personas: PersonaService
    reason: ReasonService
    reflection: ReflectionService
    trace: TraceServices
    provenance: ProvenanceService
    data: DataAdminService


def compose_application(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> ApplicationGraph:
    """Build the application graph from already-owned authority resources."""

    conversation_store = ConversationStore(paths, backend=backend)
    conversations = ConversationService(conversation_store)
    memory = compose_memory_repositories(paths, backend)
    source_services = compose_source_services(paths, backend)
    trace = compose_trace_services(paths, backend)
    memory_service = compose_memory_service(paths, memory, trace.recorder)
    config = ConfigSystem.load_scope(paths.scope)
    inbox = InboxService(paths, backend)
    deliveries = DeliveryService(DeliveryStore(paths, backend))

    def observe_reason_step(
        thread: ReasoningThread,
        step: ReasoningStep,
        trace_id: str | None,
    ) -> object:
        return publish_reason_observation(
            memory_service,
            thread=thread,
            step=step,
            source_trace_id=trace_id,
            project_root=paths.authority_root,
        )

    reason = compose_reason_service(
        paths,
        backend,
        trace.recorder,
        config,
        inbox,
        step_observer=observe_reason_step,
    )
    reflection = compose_reflection_service(
        paths,
        backend,
        reason,
        trace.recorder,
    )
    profiles = ProfileService(memory.profile)
    provenance = compose_provenance_service(
        trace.query,
        conversations=conversations,
        memory=memory_service,
        profiles=profiles,
        sources=source_services.query,
        reason=reason,
        reflection=reflection,
    )
    return ApplicationGraph(
        paths=paths,
        config=config,
        conversations=conversations,
        conversation_history=ConversationHistoryService(conversations),
        memory=memory_service,
        profiles=profiles,
        sources=source_services.query,
        source_importer=source_services.importer,
        inbox=inbox,
        deliveries=deliveries,
        personas=PersonaService(
            PersonaPromptRepository(
                backend.collection("persona_prompts"),
                paths,
            )
        ),
        reason=reason,
        reflection=reflection,
        trace=trace,
        provenance=provenance,
        data=DataAdminService(
            backend,
            conversations=conversation_store,
            memories=memory_service,
        ),
    )
