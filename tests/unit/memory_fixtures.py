"""Explicit authority composition helpers for memory tests."""

from __future__ import annotations

from pathlib import Path

from nuself.config import RuntimePaths, runtime_paths
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
from nuself.storage import StorageBackend, get_default_backend


def _resources(
    root_or_paths: Path | RuntimePaths,
    backend: StorageBackend | None,
) -> tuple[RuntimePaths, StorageBackend]:
    paths = (
        root_or_paths
        if isinstance(root_or_paths, RuntimePaths)
        else runtime_paths(root_or_paths)
    )
    return paths, backend or get_default_backend(paths.project_root)


def memory_entry_repository(
    root_or_paths: Path | RuntimePaths,
    *,
    backend: StorageBackend | None = None,
    registry: MemoryTypeRegistry | None = None,
    relation_registry: RelationDescriptorRegistry | None = None,
) -> MemoryEntryRepository:
    paths, selected_backend = _resources(root_or_paths, backend)
    return MemoryEntryRepository(
        paths,
        backend=selected_backend,
        registry=registry,
        relation_registry=relation_registry,
    )


def memory_curator_plan_store(
    root_or_paths: Path | RuntimePaths,
    *,
    backend: StorageBackend | None = None,
    registry: MemoryTypeRegistry | None = None,
) -> MemoryCuratorPlanStore:
    paths, selected_backend = _resources(root_or_paths, backend)
    return MemoryCuratorPlanStore(
        paths,
        selected_backend,
        registry=registry,
    )


def memory_candidate_repository(
    root_or_paths: Path | RuntimePaths,
    *,
    backend: StorageBackend | None = None,
    entry_repository: MemoryEntryRepository | None = None,
    profile_repository: ProfileItemRepository | None = None,
) -> MemoryCandidateRepository:
    paths, selected_backend = _resources(root_or_paths, backend)
    entries = entry_repository or MemoryEntryRepository(
        paths,
        backend=selected_backend,
    )
    profile = profile_repository or ProfileItemRepository(
        paths,
        backend=selected_backend,
    )
    return MemoryCandidateRepository(
        paths,
        backend=selected_backend,
        entry_repository=entries,
        profile_repository=profile,
    )


def source_repository(
    root_or_paths: Path | RuntimePaths,
    *,
    backend: StorageBackend | None = None,
    candidate_repository: MemoryCandidateRepository | None = None,
    profile_repository: ProfileItemRepository | None = None,
) -> SourceRepository:
    paths, selected_backend = _resources(root_or_paths, backend)
    profile = profile_repository or ProfileItemRepository(
        paths,
        backend=selected_backend,
    )
    candidates = candidate_repository or memory_candidate_repository(
        paths,
        backend=selected_backend,
        profile_repository=profile,
    )
    return SourceRepository(
        paths,
        backend=selected_backend,
        candidate_repository=candidates,
        profile_repository=profile,
    )
