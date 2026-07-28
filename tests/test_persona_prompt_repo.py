"""Tests for PersonaPromptRepository."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import pytest

from nuself.logs import read_log_events
from nuself.persona.prompt_repo import PersonaPromptRepository, create_persona_prompt


def test_concurrent_saves_preserve_name_index(tmp_path: Path) -> None:
    repo = PersonaPromptRepository(root=tmp_path / "persona_prompts")
    prompts = tuple(create_persona_prompt(f"persona-{i}", f"prompt {i}") for i in range(16))

    def save_prompt(index: int) -> None:
        local_repo = PersonaPromptRepository(root=tmp_path / "persona_prompts")
        local_repo.save(prompts[index])

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(save_prompt, range(len(prompts))))

    stored = repo.list()
    assert {prompt.name for prompt in stored} == {prompt.name for prompt in prompts}
    for prompt in prompts:
        resolved = repo.get_by_name(prompt.name)
        assert resolved is not None
        assert resolved.id == prompt.id


def test_legacy_list_reports_corruption_but_direct_get_surfaces_it(
    tmp_path: Path,
) -> None:
    prompt_root = tmp_path / "persona_prompts"
    prompt_root.mkdir()
    (prompt_root / "pp_corrupt.json").write_text("{", encoding="utf-8")
    repo = PersonaPromptRepository(root=prompt_root, project_root=tmp_path)

    assert repo.list() == ()
    event = read_log_events(project_root=tmp_path, component="persona")[-1]
    assert event.event == "record_decode_failed"
    assert event.metadata == {
        "collection": "persona_prompts",
        "record_id": "pp_corrupt",
    }
    with pytest.raises(json.JSONDecodeError):
        repo.get("pp_corrupt")
