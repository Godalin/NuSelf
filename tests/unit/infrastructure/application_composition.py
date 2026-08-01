"""Application graph composition contracts."""

from __future__ import annotations

# pyright: reportPrivateUsage=false

from pathlib import Path

from nuself.application.composition import compose_application
from nuself.config import runtime_paths
from nuself.storage import auto_backend


def test_application_graph_reuses_one_authority_repository_graph(
    tmp_path: Path,
) -> None:
    paths = runtime_paths(tmp_path)
    backend = auto_backend(tmp_path)

    graph = compose_application(paths, backend)

    assert graph.paths is paths
    assert not hasattr(graph, "_backend")
    assert not hasattr(graph, "composition_storage")
    assert graph.notifications._backend is backend
    assert graph.persona_prompts._project_root == paths.project_root
    assert graph.memory.curator_plans._backend is backend
    assert graph.memory.candidates._entry_repository is graph.memory.entries
    assert graph.memory.candidates._profile_repository is graph.memory.profile
    assert (
        graph.memory.sources._candidate_repository
        is graph.memory.candidates
    )
    assert graph.memory.sources._profile_repository is graph.memory.profile
    assert not hasattr(graph, "reason")
    assert graph.reflection_service._repository is graph.reflection
    assert graph.reflection_service._reason_service is graph.reason_service
    assert not hasattr(graph.trace, "repository")
    assert graph.trace.recorder._repository is graph.trace.query._repository
