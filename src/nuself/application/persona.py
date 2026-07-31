"""Application-owned persona prompt persistence composition."""

from __future__ import annotations

from nuself.config import RuntimePaths
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
