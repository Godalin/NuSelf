"""Shared memory-curator composition for process surfaces."""

from __future__ import annotations

from nuself.application.composition import ApplicationGraph
from nuself.memory.curator import MemoryCurator
from nuself.llm import LangChainLLMEndpoint
from nuself.memory.optimizer import (
    MemoryOptimizer,
    MemoryOptimizerSettings,
)


def compose_memory_curator(
    application: ApplicationGraph,
    *,
    langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
) -> MemoryCurator:
    """Build curation from one existing authority graph."""

    paths = application.paths
    return MemoryCurator(
        paths,
        observation_repository=application.memory.observations,
        repository=application.memory.entries,
        candidate_repository=application.memory.candidates,
        profile_repository=application.memory.profile,
        trace_recorder=application.trace.recorder,
        plan_store=application.memory.curator_plans,
        langchain_models=langchain_models,
    )


def compose_memory_optimizer(
    application: ApplicationGraph,
    *,
    settings: MemoryOptimizerSettings | None = None,
) -> MemoryOptimizer:
    """Build memory optimization from one existing authority graph."""

    return MemoryOptimizer(
        application.paths,
        settings=settings,
        repository=application.memory.entries,
        candidate_repository=application.memory.candidates,
        profile_repository=application.memory.profile,
    )
