"""Application-owned composition for memory persistence."""

from __future__ import annotations

from dataclasses import dataclass

from nuself.config import RuntimePaths
from nuself.domain.memory import (
    MemoryTypeRegistry,
    RelationDescriptorRegistry,
)
from nuself.memory.repository import (
    MemoryCandidateRepository,
    MemoryEntryRepository,
)
from nuself.memory.curator_plan import MemoryCuratorPlanStore
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
    curator_plans: MemoryCuratorPlanStore


def compose_memory_entry_repository(
    paths: RuntimePaths,
    backend: StorageBackend,
    *,
    registry: MemoryTypeRegistry | None = None,
    relation_registry: RelationDescriptorRegistry | None = None,
) -> MemoryEntryRepository:
    """Compose memory entry persistence from already-owned resources."""

    return MemoryEntryRepository(
        paths,
        backend=backend,
        registry=registry,
        relation_registry=relation_registry,
    )


def compose_memory_repositories(
    paths: RuntimePaths,
    backend: StorageBackend,
    *,
    registry: MemoryTypeRegistry | None = None,
    relation_registry: RelationDescriptorRegistry | None = None,
) -> MemoryRepositories:
    """Compose the complete memory persistence graph."""

    entries = compose_memory_entry_repository(
        paths,
        backend,
        registry=registry,
        relation_registry=relation_registry,
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
        curator_plans=MemoryCuratorPlanStore(paths, backend),
    )
