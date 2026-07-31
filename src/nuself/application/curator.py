"""Shared memory-curator composition for process surfaces."""

from __future__ import annotations

from nuself.agent.chat import ThreadStore
from nuself.application.composition import ApplicationGraph
from nuself.memory.curator import MemoryCurator


def compose_memory_curator(
    application: ApplicationGraph,
) -> MemoryCurator:
    """Build curation from one existing authority graph."""

    paths = application.paths
    return MemoryCurator(
        paths.project_root,
        thread_store=ThreadStore(
            paths.project_root,
            backend=application.backend,
        ),
        repository=application.memory.entries,
        candidate_repository=application.memory.candidates,
        profile_repository=application.memory.profile,
        trace_recorder=application.trace.recorder,
        plan_store=application.memory.curator_plans,
        backend=application.backend,
    )
