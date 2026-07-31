"""Application-owned composition for the reflection domain."""

from __future__ import annotations

from typing import TYPE_CHECKING
from nuself.config import ReflectionSettings
from nuself.config import RuntimePaths
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.notification import NotificationOutbox
from nuself.profile.repository import ProfileItemRepository
from nuself.reflection.organizer import ReflectionOrganizer
from nuself.reflection.candidates import IdeaCandidateGenerator
from nuself.reflection.relevance import LLMRelevanceGate
from nuself.reflection.repository import ReflectionRepository
from nuself.reflection.scheduler import ReflectionScheduler
from nuself.reflection.service import ReflectionService
from nuself.application.reason import compose_reason_service
from nuself.storage import StorageBackend
from nuself.trace.service import TraceRecorder

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
    paths: RuntimePaths,
    backend: StorageBackend,
    *,
    config: ReflectionSettings,
    repository: ReflectionRepository,
    outbox: NotificationOutbox,
    trace_recorder: TraceRecorder,
    memory_repository: MemoryEntryRepository,
    source_repository: SourceRepository,
    profile_repository: ProfileItemRepository,
) -> ReflectionScheduler:
    """Compose reflection orchestration from one authority-owned graph."""

    from nuself.agent.chat import ThreadStore

    schedule_collection = backend.collection("scheduler_state")
    generator = IdeaCandidateGenerator(
        paths.project_root,
        config=config,
        memory_repository=memory_repository,
        source_repository=source_repository,
        profile_repository=profile_repository,
        thread_context=ThreadStore(paths.project_root, backend=backend),
    )
    gate = LLMRelevanceGate(
        paths.project_root,
        config,
        schedule_collection=schedule_collection,
        repository=repository,
    )
    organizer = ReflectionOrganizer(
        paths.project_root,
        repository=repository,
    )
    return ReflectionScheduler(
        paths.project_root,
        config,
        schedule_collection=schedule_collection,
        repository=repository,
        outbox=outbox,
        trace_recorder=trace_recorder,
        candidate_generator=generator,
        relevance_gate=gate,
        organizer=organizer,
    )
