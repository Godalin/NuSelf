"""Application-owned composition for the reflection domain."""

from __future__ import annotations

from typing import TYPE_CHECKING
from nuself.config import ReflectionSettings
from nuself.config import RuntimePaths
from nuself.reflection.organizer import ReflectionOrganizer
from nuself.reflection.candidates import IdeaCandidateGenerator
from nuself.reflection.relevance import LLMRelevanceGate
from nuself.reflection.repository import ReflectionRepository
from nuself.reflection.scheduler import ReflectionScheduler
from nuself.reflection.service import ReflectionService
from nuself.persona import SharedPersonaDiscussionService
from nuself.application.reason import compose_reason_service
from nuself.storage import StorageBackend

if TYPE_CHECKING:
    from nuself.application.composition import ApplicationGraph


def compose_reflection_repository(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> ReflectionRepository:
    """Compose reflection persistence from already-owned resources."""

    return ReflectionRepository(paths, backend=backend)


def compose_reflection_service(
    application: "ApplicationGraph",
) -> ReflectionService:
    """Compose reflection user operations from one application graph."""

    return ReflectionService(
        application.reflection,
        compose_reason_service(application),
        application.trace.recorder,
    )


def compose_reflection_scheduler(
    application: "ApplicationGraph",
    *,
    config: ReflectionSettings,
    language_preference: str,
) -> ReflectionScheduler:
    """Compose reflection orchestration from one authority-owned graph."""

    paths = application.paths
    from nuself.application.composition import application_backend

    schedule_collection = application_backend(application).collection(
        "scheduler_state"
    )
    generator = IdeaCandidateGenerator(
        paths.project_root,
        config=config,
        memory_repository=application.memory.entries,
        source_repository=application.memory.sources,
        profile_repository=application.memory.profile,
        conversation_history=application.conversation_history,
        language_preference=language_preference,
    )
    gate = LLMRelevanceGate(
        paths.project_root,
        config,
        schedule_collection=schedule_collection,
        repository=application.reflection,
    )
    organizer = ReflectionOrganizer(
        paths.project_root,
        repository=application.reflection,
    )
    return ReflectionScheduler(
        paths.project_root,
        config,
        schedule_collection=schedule_collection,
        repository=application.reflection,
        outbox=application.notifications,
        trace_recorder=application.trace.recorder,
        candidate_generator=generator,
        relevance_gate=gate,
        organizer=organizer,
        discussion=SharedPersonaDiscussionService(
            project_root=paths.project_root,
            config=config,
            language_preference=language_preference,
        ),
    )
