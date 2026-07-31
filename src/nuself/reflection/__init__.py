"""Reflection subsystem: scheduler, repository, and proactive idea generation."""

from nuself.reflection.candidates import IdeaCandidateGenerator
from nuself.reflection.scheduler import ReflectionScheduler
from nuself.reflection.relevance import LLMRelevanceGate
from nuself.reflection.repository import (
    ReflectionEntry,
    ReflectionEntryNotFound,
    ReflectionRepository,
)
from nuself.reflection.organizer import ReflectionOrganizationResult, ReflectionOrganizer
from nuself.reflection.service import ReflectionService

__all__ = [
    "IdeaCandidateGenerator",
    "ReflectionScheduler",
    "LLMRelevanceGate",
    "ReflectionEntry",
    "ReflectionEntryNotFound",
    "ReflectionOrganizationResult",
    "ReflectionOrganizer",
    "ReflectionRepository",
    "ReflectionService",
]
