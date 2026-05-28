"""Tests for PersonaPromptRepository."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

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
