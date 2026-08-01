"""Application-owned composition for memory persistence."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.config import RuntimePaths
from nuself.memory.repository import (
    MemoryCandidateRepository,
    MemoryEntryRepository,
)
from nuself.memory.curator_plan import MemoryCuratorPlanStore
from nuself.memory.observation import MemoryObservationRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository
from nuself.storage import StorageBackend


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
