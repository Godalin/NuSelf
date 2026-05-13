"""Shared service boundary for competitive persona discussion."""

from __future__ import annotations

from pathlib import Path

from nuself.config_system import ConfigSystem, ReflectionSettings
from nuself.domain.proactive import IdeaCandidate
from nuself.llm import ChatLLM
from nuself.proactive_persona import PersonaCompetitionResult, ProactivePersonaDiscussion


class SharedPersonaDiscussionService:
    """Shared entry point for competitive persona discussion."""

    def __init__(
        self,
        project_root: Path | None = None,
        *,
        config: ReflectionSettings | None = None,
        discussion: ProactivePersonaDiscussion | None = None,
        llm: ChatLLM | None = None,
    ) -> None:
        if discussion is not None:
            self._discussion = discussion
            return
        if config is None:
            config = ConfigSystem.load(project_root=project_root).reflection
        self._discussion = ProactivePersonaDiscussion(config=config, llm=llm)

    def discuss(self, candidate: IdeaCandidate) -> PersonaCompetitionResult:
        return self._discussion.discuss(candidate)
