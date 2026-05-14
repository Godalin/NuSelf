"""Reflection subsystem: scheduler, repository, and proactive idea generation."""

from nuself.reflection.scheduler import (
    IdeaCandidateGenerator,
    ReflectionEvent,
    ReflectionScheduler,
    LLMRelevanceGate,
)
from nuself.reflection.repository import (
    ReflectionEntry,
    ReflectionEntryNotFound,
    ReflectionRepository,
)

__all__ = [
    "IdeaCandidateGenerator",
    "ReflectionEvent",
    "ReflectionScheduler",
    "LLMRelevanceGate",
    "ReflectionEntry",
    "ReflectionEntryNotFound",
    "ReflectionRepository",
]
