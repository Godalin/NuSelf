"""Explicit one-way projections across domain API boundaries."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from nuself.conversation import CompletedTurn
from nuself.memory.observation import MemoryObservation
from nuself.reason.model import ReasoningStep, ReasoningThread
from nuself.memory.repository import MemorySearchFilters
from nuself.memory.service import MemoryService
from nuself.memory.audit import MEMORY_AUDIT
from nuself.persona.audit import PERSONA_AUDIT
from nuself.persona.definition import BUILTIN_PERSONAS, PersonaDefinition


class MemoryObserver(Protocol):
    def observe(self, observation: MemoryObservation) -> MemoryObservation: ...


def publish_chat_observation(
    observer: MemoryObserver,
    *,
    turn: CompletedTurn,
    source_trace_id: str | None = None,
    project_root: Path | None = None,
) -> MemoryObservation | None:
    """Project one committed turn into memory's producer-neutral API."""

    try:
        return observer.observe(
            MemoryObservation.create(
                source_ref=turn.artifact_ref,
                fragments=(
                    f"user: {turn.user_content}",
                    f"assistant: {turn.assistant_content}",
                ),
                source_trace_id=source_trace_id,
            )
        )
    except Exception as exc:
        MEMORY_AUDIT.failure(
            exc,
            event="post_chat_observation_failed",
            project_root=project_root,
        )
        return None


def publish_reason_observation(
    observer: MemoryObserver,
    *,
    thread: ReasoningThread,
    step: ReasoningStep,
    source_trace_id: str | None = None,
    project_root: Path | None = None,
) -> MemoryObservation | None:
    """Project one committed Reason step into Memory's observation API."""

    fragments = [f"reason topic: {thread.topic}", f"reason summary: {step.summary}"]
    fragments.extend(
        f"reason finding: {item.get('label', '')}"
        for item in step.new_findings_data
        if item.get("label")
    )
    try:
        return observer.observe(
            MemoryObservation.create(
                source_ref=f"reason_step:{step.id}",
                fragments=tuple(fragments),
                source_trace_id=source_trace_id,
            )
        )
    except Exception as exc:
        MEMORY_AUDIT.failure(
            exc,
            event="post_reason_observation_failed",
            project_root=project_root,
        )
        return None


def load_personas_from_memory(
    service: MemoryService,
    *,
    project_root: Path | None = None,
) -> tuple[PersonaDefinition, ...]:
    """Project public Memory entries into Persona-owned definitions."""

    try:
        entries = service.search_entries(
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
