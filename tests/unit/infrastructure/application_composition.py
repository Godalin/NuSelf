"""Application graph composition contracts."""

from __future__ import annotations

# pyright: reportPrivateUsage=false

from pathlib import Path

from pytest import MonkeyPatch

from nuself.application.composition import compose_application
from nuself.config.settings import ConfigSystem
from nuself.config.settings import runtime_paths
from nuself.config.scope import (
    resolve_runtime_paths,
    resolve_scope,
    scope_from_authority_root,
)
from nuself.storage.authority import auto_backend


def test_application_graph_reuses_one_authority_repository_graph(
    tmp_path: Path,
) -> None:
    paths = runtime_paths(tmp_path)
    backend = auto_backend(tmp_path)

    graph = compose_application(paths, backend)

    assert graph.paths is paths
    assert graph.config == ConfigSystem.load_scope(
        scope_from_authority_root(tmp_path)
    )
    assert not hasattr(graph, "_backend")
    assert not hasattr(graph, "composition_storage")
    assert graph.inbox._backend is backend
    assert graph.deliveries._store._backend is backend
    assert graph.personas._repository._project_root == paths.authority_root
    memory = graph.memory_workflows._repositories
    assert memory.curator_plans._backend is backend
    assert graph.memory._repository is memory.entries
    assert memory.candidates._entry_repository is memory.entries
    assert memory.candidates._profile_repository is memory.profile
    assert not hasattr(graph.sources._repository, "_candidate_repository")
    assert not hasattr(graph.sources._repository, "_profile_repository")
    assert not hasattr(graph, "reason_service")
    assert not hasattr(graph, "reason_workspace")
    assert graph.reason._workspace_store is not None
    assert graph.reflection._repository is not None
    assert graph.reflection._reason_service is graph.reason
    assert not hasattr(graph.trace, "repository")
    assert graph.trace.recorder._repository is graph.trace.query._repository


def test_application_graph_uses_resolved_workspace_config_layers(
    tmp_path: Path,
) -> None:
    user_root = (tmp_path / "user").resolve()
    workspace = (tmp_path / "workspace").resolve()
    user_root.mkdir()
    (workspace / ".nuself").mkdir(parents=True)
    (user_root / "config.yaml").write_text(
        "chat:\n  language_preference: zh-CN\n",
        encoding="utf-8",
    )
    (workspace / ".nuself" / "config.yaml").write_text(
        "chat:\n  context:\n    recent_messages: 7\n",
        encoding="utf-8",
    )
    scope = resolve_scope(
        workspace=workspace,
        environ={"NUSELF_HOME": str(user_root)},
    )
    paths = resolve_runtime_paths(scope)

    graph = compose_application(
        paths,
        auto_backend(paths.authority_root),
    )

    assert graph.config.chat.language_preference == "zh-CN"
    assert graph.config.chat.context.recent_messages == 7


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
        "nuself.reason.composition.configured_langchain_chat_models",
        configured_models,
    )
    monkeypatch.setattr(
        "nuself.reason.composition.generate_reasoning_prompt",
        generate_prompt,
    )

    graph = compose_application(paths, backend)
    assert model_calls == 0

    thread = graph.reason.start_thread("Composed topic")

    assert thread.reasoning_prompt == "Composed prompt."
    assert model_calls == 1
