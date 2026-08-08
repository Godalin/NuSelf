"""Resolved resources borrowed by one conversation runtime."""

from __future__ import annotations

from dataclasses import dataclass
from nuself.agent.outcome import ToolOutcomeProjection
from nuself.agent.tools.resources import ToolResources
from nuself.config.settings import ReflectionSettings
from nuself.conversation import ConversationService
from nuself.persona.definition import PersonaDefinition
from nuself.trace.service import TraceRecorder


@dataclass(frozen=True)
class ConversationResources:
    """One authority-resolved capability snapshot; owns no lifecycle."""

    tools: ToolResources
    trace_recorder: TraceRecorder
    conversation_store: ConversationService
    personas: tuple[PersonaDefinition, ...]
    reflection_settings: ReflectionSettings
    language_preference: str = "en"
    tool_outcomes: ToolOutcomeProjection | None = None
