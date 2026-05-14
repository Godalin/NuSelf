"""Reflection subsystem: scheduler, repository, and proactive idea generation."""

from nuself.reflection.scheduler import (
    IdeaCandidateGenerator,
    ReflectionEvent,
    ReflectionScheduler,
    RelevanceGate,
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
    "RelevanceGate",
    "ReflectionEntry",
    "ReflectionEntryNotFound",
    "ReflectionRepository",
]
