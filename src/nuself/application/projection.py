"""Explicit one-way projections across domain API boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from nuself.conversation import CompletedTurn
from nuself.memory.observation import MemoryObservation
from nuself.memory.repository import MemoryEntryRepository, MemorySearchFilters
from nuself.persona.audit import PERSONA_AUDIT
from nuself.persona.definition import BUILTIN_PERSONAS, PersonaDefinition


class MemoryObserver(Protocol):
    def observe(self, observation: MemoryObservation) -> MemoryObservation: ...


def publish_chat_observation(
    observer: MemoryObserver,
    *,
    turn: CompletedTurn,
    source_trace_id: str | None = None,
) -> MemoryObservation:
    """Project one committed turn into memory's producer-neutral API."""

    source_identity = (
        f"{turn.conversation_id}:{turn.start_index}:{turn.end_index}"
    )
    source_ref = f"interaction:{uuid5(NAMESPACE_URL, source_identity).hex}"
    return observer.observe(
        MemoryObservation.create(
            source_ref=source_ref,
            fragments=(
                f"user: {turn.user_content}",
                f"assistant: {turn.assistant_content}",
            ),
            source_trace_id=source_trace_id,
        )
    )


def load_personas_from_memory(
    repository: MemoryEntryRepository,
    *,
    project_root: Path | None = None,
) -> tuple[PersonaDefinition, ...]:
    """Project public Memory entries into Persona-owned definitions."""

    try:
        entries = repository.search(
            "",
            filters=MemorySearchFilters(type="persona_instruction"),
        )
    except RuntimeError as exc:
        PERSONA_AUDIT.failure(
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
