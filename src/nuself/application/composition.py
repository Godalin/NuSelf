"""Complete application service graph for one authority."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.application.memory import (
    MemoryRepositories,
    compose_memory_repositories,
)
from nuself.application.data_admin import DataAdminService
from nuself.application.trace import TraceServices, compose_trace_services
from nuself.config import RuntimePaths
from nuself.conversation import ConversationHistoryService, ConversationStore
from nuself.notification import NotificationOutbox
from nuself.persona.prompt_repo import PersonaPromptRepository
from nuself.reason.repository import ReasonRepository
from nuself.reflection.repository import ReflectionRepository
from nuself.storage import StorageBackend, StorageCollection


@dataclass(frozen=True)
class ApplicationGraph:
    """Concrete services sharing one selected authority."""

    paths: RuntimePaths
    conversations: ConversationStore
    conversation_history: ConversationHistoryService
    memory: MemoryRepositories
    notifications: NotificationOutbox
    persona_prompts: PersonaPromptRepository
    reason: ReasonRepository
    reflection: ReflectionRepository
    reflection_schedule: StorageCollection
    trace: TraceServices
    data: DataAdminService


def compose_application(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> ApplicationGraph:
    """Build the application graph from already-owned authority resources."""

    conversations = ConversationStore(paths, backend=backend)
    memory = compose_memory_repositories(paths, backend)
    return ApplicationGraph(
        paths=paths,
        conversations=conversations,
        conversation_history=ConversationHistoryService(conversations),
        memory=memory,
        notifications=NotificationOutbox(paths, backend),
        persona_prompts=PersonaPromptRepository(
            backend.collection("persona_prompts"),
            paths,
        ),
        reason=ReasonRepository(paths, backend=backend),
        reflection=ReflectionRepository(paths, backend=backend),
        reflection_schedule=backend.collection("scheduler_state"),
        trace=compose_trace_services(paths, backend),
        data=DataAdminService(
            backend,
            conversations=conversations,
            memories=memory.entries,
        ),
    )
