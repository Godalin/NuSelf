"""Resolved resources borrowed by one conversation runtime."""

from __future__ import annotations

from dataclasses import dataclass
from nuself.agent.tools.resources import ToolResources
from nuself.agent.chat.thread import ThreadStore
from nuself.persona.definition import PersonaDefinition
from nuself.trace.service import TraceRecorder


@dataclass(frozen=True)
class ConversationResources:
    """One authority-resolved capability snapshot; owns no lifecycle."""

    tools: ToolResources
    trace_recorder: TraceRecorder
    thread_store: ThreadStore
    personas: tuple[PersonaDefinition, ...]
