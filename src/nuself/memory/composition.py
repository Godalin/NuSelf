"""Memory-owned persistence and workflow composition."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.agent.structured import LangChainStructuredAgent
from nuself.config import RuntimePaths, SystemConfig
from nuself.llm import (
    LangChainLLMEndpoint,
    configured_langchain_chat_models,
)
from nuself.memory.curator import MemoryCurator
from nuself.memory.curator_contract import CuratorActionsOutput
from nuself.memory.repository import (
    MemoryCandidateRepository,
    MemoryEntryRepository,
)
from nuself.memory.curator_plan import MemoryCuratorPlanStore
from nuself.memory.observation import MemoryObservationRepository
from nuself.memory.optimizer import (
    MemoryOptimizer,
    MemoryOptimizerSettings,
    OptimizeActionsOutput,
)
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository
from nuself.storage.contract import StorageBackend
from nuself.trace.service import TraceRecorder


@dataclass(frozen=True)
class MemoryRepositories:
    """Memory repositories sharing one authority and dependency graph."""

    entries: MemoryEntryRepository
    candidates: MemoryCandidateRepository
    sources: SourceRepository
    profile: ProfileItemRepository
    observations: MemoryObservationRepository
    curator_plans: MemoryCuratorPlanStore


def compose_memory_repositories(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> MemoryRepositories:
    """Compose the complete memory persistence graph."""

    entries = MemoryEntryRepository(
        paths,
        backend=backend,
    )
    profile = ProfileItemRepository(paths, backend=backend)
    candidates = MemoryCandidateRepository(
        paths,
        backend=backend,
        entry_repository=entries,
        profile_repository=profile,
    )
    sources = SourceRepository(
        paths,
        backend=backend,
        candidate_repository=candidates,
        profile_repository=profile,
    )
    return MemoryRepositories(
        entries=entries,
        candidates=candidates,
        sources=sources,
        profile=profile,
        observations=MemoryObservationRepository(backend),
        curator_plans=MemoryCuratorPlanStore(paths, backend),
    )


def compose_memory_curator(
    paths: RuntimePaths,
    repositories: MemoryRepositories,
    trace_recorder: TraceRecorder,
    config: SystemConfig,
    *,
    langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
) -> MemoryCurator:
    """Build curation from one existing authority graph."""

    models = (
        langchain_models
        if langchain_models is not None
        else configured_langchain_chat_models(
            paths.authority_root,
            config=config,
        )
    )
    return MemoryCurator(
        paths,
        agent=LangChainStructuredAgent(
            CuratorActionsOutput,
            endpoints=models,
            project_root=paths.authority_root,
            component="memory",
        ),
        observation_repository=repositories.observations,
        repository=repositories.entries,
        candidate_repository=repositories.candidates,
        profile_repository=repositories.profile,
        trace_recorder=trace_recorder,
        plan_store=repositories.curator_plans,
    )


def compose_memory_optimizer(
    paths: RuntimePaths,
    repositories: MemoryRepositories,
    config: SystemConfig,
    *,
    settings: MemoryOptimizerSettings | None = None,
) -> MemoryOptimizer:
    """Build memory optimization from one existing authority graph."""

    return MemoryOptimizer(
        paths,
        agent=LangChainStructuredAgent(
            OptimizeActionsOutput,
            endpoints=configured_langchain_chat_models(
                paths.authority_root,
                config=config,
            ),
            project_root=paths.authority_root,
            component="memory",
        ),
        settings=settings,
        repository=repositories.entries,
        candidate_repository=repositories.candidates,
        profile_repository=repositories.profile,
    )
