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
from nuself.memory.query import MemoryService
from nuself.persona.prompt_repo import PersonaPromptRepository
from nuself.reason.repository import ReasonRepository
from nuself.reason.service import ReasonService
from nuself.reflection.repository import ReflectionRepository
from nuself.reflection.organizer import ReflectionOrganizer
from nuself.reflection.service import ReflectionService
from nuself.storage import StorageBackend, StorageCollection
from nuself.workspace import PrivateWorkspaceStore


@dataclass(frozen=True)
class ApplicationGraph:
    """Concrete services sharing one selected authority."""

    paths: RuntimePaths
    conversations: ConversationStore
    conversation_history: ConversationHistoryService
    memory: MemoryRepositories
    memory_service: MemoryService
    notifications: NotificationOutbox
    persona_prompts: PersonaPromptRepository
    reason_workspace: PrivateWorkspaceStore
    reason_service: ReasonService
    reflection: ReflectionRepository
    reflection_service: ReflectionService
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
    trace = compose_trace_services(paths, backend)
    reason = ReasonRepository(paths, backend=backend)
    reflection = ReflectionRepository(paths, backend=backend)
    reason_workspace = PrivateWorkspaceStore(paths, scope="reason")
    reason_service = ReasonService(
        paths.project_root,
        repository=reason,
        workspace_store=reason_workspace,
        trace_recorder=trace.recorder,
    )
    return ApplicationGraph(
        paths=paths,
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
        reason_workspace=reason_workspace,
        reason_service=reason_service,
        reflection=reflection,
        reflection_service=ReflectionService(
            reflection,
            reason_service,
            trace.recorder,
            ReflectionOrganizer(
                paths.project_root,
                repository=reflection,
            ),
        ),
        reflection_schedule=backend.collection("scheduler_state"),
        trace=trace,
        data=DataAdminService(
            backend,
            conversations=conversations,
            memories=memory.entries,
        ),
    )
