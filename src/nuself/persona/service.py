"""Authority-scoped Persona user and workflow capabilities."""

from __future__ import annotations

from nuself.persona.prompt_repo import (
    PersonaPrompt,
    PersonaPromptRepository,
    create_persona_prompt,
)


class PersonaService:
    """Manage and resolve dynamic personas without exposing persistence."""

    def __init__(self, repository: PersonaPromptRepository) -> None:
        self._repository = repository

    def list_prompts(self) -> tuple[PersonaPrompt, ...]:
        return self._repository.list()

    def list(self) -> tuple[PersonaPrompt, ...]:
        return self._repository.list()

    def get_prompt(self, prompt_id: str) -> PersonaPrompt | None:
        return self._repository.get(prompt_id)

    def get(self, prompt_id: str) -> PersonaPrompt | None:
        return self._repository.get(prompt_id)

    def get_by_name(self, name: str) -> PersonaPrompt | None:
        return self._repository.get_by_name(name)

    def resolve_prompt(self, name_or_id: str) -> PersonaPrompt | None:
        return self._repository.resolve(name_or_id)

    def resolve(self, name_or_id: str) -> PersonaPrompt | None:
        return self._repository.resolve(name_or_id)

    def create_or_replace(self, name: str, prompt_text: str) -> PersonaPrompt:
        proposed = create_persona_prompt(name, prompt_text)
        existing = self._repository.get_by_name(name)
        if existing is not None:
            proposed = PersonaPrompt(
                id=existing.id,
                name=name,
                prompt=prompt_text,
                disabled=existing.disabled,
                created_at=existing.created_at,
                updated_at=proposed.updated_at,
            )
        self._repository.save(proposed)
        return proposed

    def delete_prompt(self, prompt_id: str) -> None:
        self._repository.delete(prompt_id)

    def save(self, prompt: PersonaPrompt) -> None:
        self._repository.save(prompt)

    def delete(self, prompt_id: str) -> None:
        self._repository.delete(prompt_id)

    def set_enabled(self, prompt_id: str, *, enabled: bool) -> None:
        self._repository.set_disabled(prompt_id, not enabled)

    def set_disabled(self, prompt_id: str, disabled: bool) -> None:
        self._repository.set_disabled(prompt_id, disabled)
