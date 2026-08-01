"""Shared memory-curator composition for process surfaces."""

from __future__ import annotations

from nuself.application.composition import ApplicationGraph
from nuself.agent.structured import LangChainStructuredAgent
from nuself.memory.curator import MemoryCurator
from nuself.memory.curator_contract import CuratorActionsOutput
from nuself.llm import (
    LangChainLLMEndpoint,
    configured_langchain_chat_models,
)
from nuself.memory.optimizer import (
    MemoryOptimizer,
    MemoryOptimizerSettings,
    OptimizeActionsOutput,
)


def compose_memory_curator(
    application: ApplicationGraph,
    *,
    langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
) -> MemoryCurator:
    """Build curation from one existing authority graph."""

    paths = application.paths
    models = (
        langchain_models
        if langchain_models is not None
        else configured_langchain_chat_models(
            paths.project_root,
            config=application.config,
        )
    )
    return MemoryCurator(
        paths,
        agent=LangChainStructuredAgent(
            CuratorActionsOutput,
            endpoints=models,
            project_root=paths.project_root,
            component="memory",
        ),
        observation_repository=application.memory.observations,
        repository=application.memory.entries,
        candidate_repository=application.memory.candidates,
        profile_repository=application.memory.profile,
        trace_recorder=application.trace.recorder,
        plan_store=application.memory.curator_plans,
    )


def compose_memory_optimizer(
    application: ApplicationGraph,
    *,
    settings: MemoryOptimizerSettings | None = None,
) -> MemoryOptimizer:
    """Build memory optimization from one existing authority graph."""

    return MemoryOptimizer(
        application.paths,
        agent=LangChainStructuredAgent(
            OptimizeActionsOutput,
            endpoints=configured_langchain_chat_models(
                application.paths.project_root,
                config=application.config,
            ),
            project_root=application.paths.project_root,
            component="memory",
        ),
        settings=settings,
        repository=application.memory.entries,
        candidate_repository=application.memory.candidates,
        profile_repository=application.memory.profile,
    )
