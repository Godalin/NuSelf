"""Resolved resources borrowed by one conversation runtime."""

from __future__ import annotations

from dataclasses import dataclass
from nuself.agent.tools.resources import ToolResources
from nuself.conversation import ConversationStore
from nuself.persona.definition import PersonaDefinition
from nuself.trace.service import TraceRecorder


@dataclass(frozen=True)
class ConversationResources:
    """One authority-resolved capability snapshot; owns no lifecycle."""

    tools: ToolResources
    trace_recorder: TraceRecorder
    conversation_store: ConversationStore
    personas: tuple[PersonaDefinition, ...]
    language_preference: str = "en"
