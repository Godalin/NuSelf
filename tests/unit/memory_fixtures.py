"""Explicit authority composition helpers for memory tests."""

from __future__ import annotations

from pathlib import Path

from conversation_fixtures import ConversationStore
from nuself.agent.structured import StructuredAgent
from nuself.application import compose_trace_services
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
from nuself.memory.curator_contract import (
    CuratorActionsOutput,
    MemoryCuratorSettings,
)
from nuself.memory.curator import MemoryCurator as _MemoryCurator
from nuself.memory.observation import MemoryObservation, MemoryObservationRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository
from nuself.storage import StorageBackend, get_default_backend
from nuself.trace.service import TraceRecorder


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


class MemoryCurator(_MemoryCurator):
    """Test convenience wrapper with explicit authority resources."""

    def __init__(
        self,
        project_root: Path,
        *,
        agent: StructuredAgent[CuratorActionsOutput],
        settings: MemoryCuratorSettings | None = None,
        conversation_store: ConversationStore | None = None,
        repository: MemoryEntryRepository | None = None,
        candidate_repository: MemoryCandidateRepository | None = None,
        profile_repository: ProfileItemRepository | None = None,
        registry: MemoryTypeRegistry | None = None,
        trace_recorder: TraceRecorder | None = None,
        plan_store: MemoryCuratorPlanStore | None = None,
        backend: StorageBackend | None = None,
    ) -> None:
        paths, selected_backend = _resources(project_root, backend)
        self._test_paths = paths
        self._test_conversations = conversation_store or ConversationStore(
            paths.project_root, backend=selected_backend
        )
        self._test_observations = MemoryObservationRepository(selected_backend)
        entries = repository or memory_entry_repository(
            paths,
            backend=selected_backend,
            registry=registry,
        )
        profile = profile_repository or ProfileItemRepository(
            paths,
            backend=selected_backend,
        )
        candidates = candidate_repository or memory_candidate_repository(
            paths,
            backend=selected_backend,
            entry_repository=entries,
            profile_repository=profile,
        )
        super().__init__(
            paths,
            agent=agent,
            settings=settings,
            observation_repository=self._test_observations,
            repository=entries,
            candidate_repository=candidates,
            profile_repository=profile,
            registry=registry,
            trace_recorder=trace_recorder
            or compose_trace_services(paths, selected_backend).recorder,
            plan_store=plan_store
            or memory_curator_plan_store(
                paths,
                backend=selected_backend,
                registry=registry,
            ),
        )

    def run_once(
        self,
        observation_id: str = "default",
        *,
        source_trace_id: str | None = None,
    ):
        observation = self.prepare_observation(
            observation_id,
            source_trace_id=source_trace_id,
        )
        if observation is None:
            from nuself.memory.curator_contract import MemoryCuratorResult
            return MemoryCuratorResult(0, 0, 0, 0, self._test_paths.logs_dir / "memory.log")
        return super().run_once(observation.id)

    def prepare_observation(
        self,
        conversation_id: str = "default",
        *,
        source_trace_id: str | None = None,
    ) -> MemoryObservation | None:
        prefix = f"test-interaction:{conversation_id}:"
        pending = [
            item for item in self._test_observations.pending()
            if item.source_ref.startswith(prefix)
        ]
        if pending:
            return pending[0]
        processed_end = 0
        for item in self._test_observations.list():
            source_ref = item.source_ref
            if not source_ref.startswith(prefix):
                continue
            try:
                processed_end = max(processed_end, int(source_ref.rsplit("-", 1)[1]))
            except (IndexError, ValueError):
                continue
        state = self._test_conversations.load(conversation_id)
        start = max(processed_end, state.message_start_index)
        offset = start - state.message_start_index
        messages = state.messages[offset:]
        if not messages:
            return None
        source_ref = f"{prefix}{start}-{state.next_message_index}"
        observation = self._test_observations.observe(
            MemoryObservation.create(
                source_ref=source_ref,
                fragments=tuple(
                    f"{message.role}: {message.content}" for message in messages
                ),
                source_trace_id=source_trace_id,
            )
        )
        return observation
