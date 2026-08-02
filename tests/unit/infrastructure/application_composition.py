"""Application graph composition contracts."""

from __future__ import annotations

# pyright: reportPrivateUsage=false

from pathlib import Path

from pytest import MonkeyPatch

from nuself.application.composition import compose_application
from nuself.config import ConfigSystem
from nuself.config import runtime_paths
from nuself.storage import auto_backend


def test_application_graph_reuses_one_authority_repository_graph(
    tmp_path: Path,
) -> None:
    paths = runtime_paths(tmp_path)
    backend = auto_backend(tmp_path)

    graph = compose_application(paths, backend)

    assert graph.paths is paths
    assert graph.config == ConfigSystem.load(project_root=tmp_path)
    assert not hasattr(graph, "_backend")
    assert not hasattr(graph, "composition_storage")
    assert graph.notifications._backend is backend
    assert graph.persona_prompts._project_root == paths.authority_root
    assert graph.memory.curator_plans._backend is backend
    assert graph.memory_service._repository is graph.memory.entries
    assert graph.memory.candidates._entry_repository is graph.memory.entries
    assert graph.memory.candidates._profile_repository is graph.memory.profile
    assert (
        graph.memory.sources._candidate_repository
        is graph.memory.candidates
    )
    assert graph.memory.sources._profile_repository is graph.memory.profile
    assert not hasattr(graph, "reason")
    assert graph.reason_service._workspace_store is graph.reason_workspace
    assert graph.reflection_service._repository is graph.reflection
    assert graph.reflection_service._reason_service is graph.reason_service
    assert not hasattr(graph.trace, "repository")
    assert graph.trace.recorder._repository is graph.trace.query._repository


def test_reason_prompt_models_are_composed_lazily(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    paths = runtime_paths(tmp_path)
    backend = auto_backend(tmp_path)
    model_calls = 0

    def configured_models(*args: object, **kwargs: object) -> tuple[object, ...]:
        nonlocal model_calls
        del args, kwargs
        model_calls += 1
        return ()

    def generate_prompt(*args: object, **kwargs: object) -> str:
        del args
        assert kwargs["project_root"] == paths.authority_root
        assert kwargs["endpoints"] == ()
        return "Composed prompt."

    monkeypatch.setattr(
        "nuself.application.reason.configured_langchain_chat_models",
        configured_models,
    )
    monkeypatch.setattr(
        "nuself.application.reason.generate_reasoning_prompt",
        generate_prompt,
    )

    graph = compose_application(paths, backend)
    assert model_calls == 0

    thread = graph.reason_service.start_thread("Composed topic")

    assert thread.reasoning_prompt == "Composed prompt."
    assert model_calls == 1
