"""Application-owned persona prompt persistence composition."""

from __future__ import annotations

from pathlib import Path

from nuself.config import RuntimePaths
from nuself.memory.repository import MemoryEntryRepository, MemorySearchFilters
from nuself.persona.audit import report_persona_failure
from nuself.persona.definition import BUILTIN_PERSONAS, PersonaDefinition
from nuself.persona.prompt_repo import PersonaPromptRepository
from nuself.storage import StorageBackend


def compose_persona_prompt_repository(
    paths: RuntimePaths,
    backend: StorageBackend,
) -> PersonaPromptRepository:
    """Build persona prompt persistence from explicit authority resources."""

    return PersonaPromptRepository(
        backend.collection("persona_prompts"),
        paths,
    )


def load_personas_from_memory(
    repository: MemoryEntryRepository,
    *,
    project_root: Path | None = None,
) -> tuple[PersonaDefinition, ...]:
    """Project memory instructions into persona-owned DTOs at composition."""

    try:
        entries = repository.search(
            "",
            filters=MemorySearchFilters(type="persona_instruction"),
        )
    except RuntimeError as exc:
        report_persona_failure(
            exc,
            event="persona_definition_load_failed",
            project_root=project_root,
        )
        return BUILTIN_PERSONAS
    definitions = tuple(
        PersonaDefinition(id=persona_id, description=description)
        for entry in entries
        for memory in (entry.to_memory_object(),)
        for persona_id in (memory.payload.get("persona_id"),)
        for description in (memory.payload.get("description"),)
        if isinstance(persona_id, str) and isinstance(description, str)
    )
    return definitions or BUILTIN_PERSONAS
