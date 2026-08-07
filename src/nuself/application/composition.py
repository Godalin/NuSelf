"""Complete application service graph for one authority."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.memory.composition import (
    MemoryWorkflowService,
    compose_memory_repositories,
)
from nuself.reason.composition import compose_reason_service
from nuself.application.data import DataAdminService
from nuself.trace.composition import TraceServices, compose_trace_services
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
from nuself.storage.contract import StorageBackend
from nuself.source.composition import compose_source_service
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
    memory_workflows: MemoryWorkflowService
    sources: SourceService
    inbox: InboxService
    deliveries: DeliveryService
    personas: PersonaService
    reason: ReasonService
    reflection: ReflectionService
    trace: TraceServices
    data: DataAdminService


def compose_application(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> ApplicationGraph:
    """Build the application graph from already-owned authority resources."""

    conversation_store = ConversationStore(paths, backend=backend)
    conversations = ConversationService(conversation_store)
    memory = compose_memory_repositories(paths, backend)
    sources = compose_source_service(paths, backend)
    trace = compose_trace_services(paths, backend)
    config = ConfigSystem.load_scope(paths.scope)
    inbox = InboxService(paths, backend)
    deliveries = DeliveryService(DeliveryStore(paths, backend))
    reason = compose_reason_service(
        paths,
        backend,
        trace.recorder,
        config,
        inbox,
    )
    reflection = compose_reflection_service(
        paths,
        backend,
        reason,
        trace.recorder,
    )
    return ApplicationGraph(
        paths=paths,
        config=config,
        conversations=conversations,
        conversation_history=ConversationHistoryService(conversations),
        memory=MemoryService(memory.entries, memory.candidates),
        profiles=ProfileService(memory.profile),
        memory_workflows=MemoryWorkflowService(paths, memory),
        sources=sources,
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
        data=DataAdminService(
            backend,
            conversations=conversation_store,
            memories=memory.entries,
        ),
    )
