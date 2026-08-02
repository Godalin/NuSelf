"""Tests for PersonaPromptRepository."""

from __future__ import annotations

# pyright: reportPrivateUsage=false

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from nuself.config import runtime_paths
from nuself.persona.prompt_repo import PersonaPromptRepository, create_persona_prompt
from nuself.storage.authority import (
    _create_sqlite_backend,
    open_sqlite_backend,
)
from nuself.storage.workspace import ScopedWorkspace, SqliteStore, WorkspaceCollection


def _durable_repo(tmp_path: Path) -> PersonaPromptRepository:
    backend = open_sqlite_backend(db_path=tmp_path / "nuself.sqlite")
    return PersonaPromptRepository(
        backend.collection("persona_prompts"),
        runtime_paths(tmp_path),
    )


def _workspace_repo(tmp_path: Path) -> PersonaPromptRepository:
    database = tmp_path / "workspace.sqlite"
    _create_sqlite_backend(db_path=database).close()
    store = SqliteStore(database)
    workspace = ScopedWorkspace(store, ("reason-1",))
    return PersonaPromptRepository(
        WorkspaceCollection(workspace, namespace="persona_prompts"),
        runtime_paths(tmp_path),
    )


def test_concurrent_saves_preserve_all_prompts(tmp_path: Path) -> None:
    _create_sqlite_backend(
        db_path=tmp_path / "nuself.sqlite",
    ).close()
    prompts = tuple(
        create_persona_prompt(f"persona-{i}", f"prompt {i}") for i in range(16)
    )

    def save_prompt(index: int) -> None:
        _durable_repo(tmp_path).save(prompts[index])

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save_prompt, range(len(prompts))))

    stored = _durable_repo(tmp_path).list()
    assert {prompt.name for prompt in stored} == {
        prompt.name for prompt in prompts
    }


def test_name_resolution_is_derived_from_collection_records(
    tmp_path: Path,
) -> None:
    _create_sqlite_backend(
        db_path=tmp_path / "nuself.sqlite",
    ).close()
    repo = _durable_repo(tmp_path)
    original = create_persona_prompt("reviewer", "Review carefully.")
    repo.save(original)
    renamed = replace(
        original,
        name="critic",
        prompt="Critique carefully.",
    )

    repo.save(renamed)

    assert repo.get_by_name("reviewer") is None
    assert repo.get_by_name("critic") == renamed


def test_workspace_collection_round_trips_thread_personas(
    tmp_path: Path,
) -> None:
    repo = _workspace_repo(tmp_path)
    prompt = create_persona_prompt("planner", "Plan carefully.")

    repo.save(prompt)

    assert repo.get(prompt.id) == prompt
    assert repo.get_by_name("planner") == prompt
    assert repo.list() == (prompt,)
    repo.delete(prompt.id)
    assert repo.list() == ()


def test_workspace_persona_collection_is_isolated_from_other_scratch(
    tmp_path: Path,
) -> None:
    database = tmp_path / "workspace.sqlite"
    _create_sqlite_backend(db_path=database).close()
    store = SqliteStore(database)
    workspace = ScopedWorkspace(store, ("reason-1",))
    workspace.put("note-1", {"text": "private note"}, sub="notes")
    repo = PersonaPromptRepository(
        WorkspaceCollection(workspace, namespace="persona_prompts"),
        runtime_paths(tmp_path),
    )

    assert repo.list() == ()
