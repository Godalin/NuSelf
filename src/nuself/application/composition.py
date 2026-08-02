"""Complete application service graph for one authority."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.memory.composition import (
    MemoryRepositories,
    compose_memory_repositories,
)
from nuself.reason.composition import ReasonResources, compose_reason_resources
from nuself.application.data_admin import DataAdminService
from nuself.trace.composition import TraceServices, compose_trace_services
from nuself.config import ConfigSystem, RuntimePaths, SystemConfig
from nuself.conversation import ConversationHistoryService, ConversationStore
from nuself.notification.outbox import NotificationOutbox
from nuself.memory.service import MemoryService
from nuself.persona.prompt_repo import PersonaPromptRepository
from nuself.reflection.composition import (
    ReflectionResources,
    compose_reflection_resources,
)
from nuself.storage.contract import StorageBackend


@dataclass(frozen=True)
class ApplicationGraph:
    """Concrete services sharing one selected authority."""

    paths: RuntimePaths
    config: SystemConfig
    conversations: ConversationStore
    conversation_history: ConversationHistoryService
    memory: MemoryRepositories
    memory_service: MemoryService
    notifications: NotificationOutbox
    persona_prompts: PersonaPromptRepository
    reason: ReasonResources
    reflection: ReflectionResources
    trace: TraceServices
    data: DataAdminService


def compose_application(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> ApplicationGraph:
    """Build the application graph from already-owned authority resources."""

    conversations = ConversationStore(paths, backend=backend)
    memory = compose_memory_repositories(paths, backend)
    trace = compose_trace_services(paths, backend)
    config = ConfigSystem.load_scope(paths.scope)
    reason = compose_reason_resources(
        paths,
        backend,
        trace.recorder,
        config,
    )
    reflection = compose_reflection_resources(
        paths,
        backend,
        reason.service,
        trace.recorder,
    )
    return ApplicationGraph(
        paths=paths,
        config=config,
        conversations=conversations,
        conversation_history=ConversationHistoryService(conversations),
        memory=memory,
        memory_service=MemoryService(
            memory.entries,
            memory.sources,
            memory.profile,
        ),
        notifications=NotificationOutbox(paths, backend),
        persona_prompts=PersonaPromptRepository(
            backend.collection("persona_prompts"),
            paths,
        ),
        reason=reason,
        reflection=reflection,
        trace=trace,
        data=DataAdminService(
            backend,
            conversations=conversations,
            memories=memory.entries,
        ),
    )
