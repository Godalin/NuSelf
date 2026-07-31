"""Proactive reflection candidate generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from nuself.agent.errors import AgentError
from nuself.agent.structured import StructuredAgent, default_structured_agent
from nuself.clock import utc_now_iso
from nuself.config import ConfigSystem, ReflectionSettings
from nuself.domain.proactive import IdeaCandidate, IdeaCandidateType
from nuself.memory.repository import MemoryEntryRepository
from nuself.memory.source_repository import SourceRepository
from nuself.profile.repository import ProfileItemRepository
from nuself.reflection.audit import report_reflection_failure, write_reflection_audit


class CandidateItemOutput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1)
    candidate_type: IdeaCandidateType
    confidence: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    urgency: float = Field(ge=0, le=1)
    interruption_cost: float = Field(ge=0, le=1)


class CandidateListOutput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    candidates: list[CandidateItemOutput] = Field(max_length=3)


class ConversationContextProvider(Protocol):
    """Provide recent conversation context without exposing chat storage."""

    def recent_context(
        self,
        max_conversations: int,
        max_messages: int,
    ) -> str: ...


class IdeaCandidateGenerator:
    """Generate ideas from explicitly supplied personal-context stores."""

    def __init__(
        self,
        project_root: Path,
        *,
        config: ReflectionSettings,
        memory_repository: MemoryEntryRepository,
        source_repository: SourceRepository,
        profile_repository: ProfileItemRepository,
        conversation_context: ConversationContextProvider,
        agent: StructuredAgent[CandidateListOutput] | None = None,
    ) -> None:
        self._project_root = project_root
        self._memory_repository = memory_repository
        self._source_repository = source_repository
        self._profile_repository = profile_repository
        self._conversation_context = conversation_context
        self._agent = agent or default_structured_agent(
            CandidateListOutput,
            project_root=project_root,
            component="reflection",
        )
        self._language_preference = ConfigSystem.load(
            project_root=project_root
        ).chat.language_preference

    def generate(self, max_candidates: int = 3) -> list[IdeaCandidate]:
        context = self._collect_context()
        if context.is_empty():
            write_reflection_audit(
                "candidate_generation_skipped",
                "no context available for idea generation",
                project_root=self._project_root,
                metadata={"reason": "empty_context"},
            )
            return []
        try:
            output = self._agent.invoke(self._messages(context))
        except AgentError as exc:
            report_reflection_failure(
                exc,
                event="candidate_generation_failed",
                message=f"failed to generate candidates: {type(exc).__name__}",
                project_root=self._project_root,
                metadata=None,
            )
            return []
        try:
            candidates = self._convert(output, max_candidates)
        except ValueError as exc:
            report_reflection_failure(
                exc,
                event="candidate_generation_failed",
                message=f"failed to generate candidates: {type(exc).__name__}",
                project_root=self._project_root,
                metadata=None,
            )
            return []
        if not candidates:
            write_reflection_audit(
                "cycle_no_candidates",
                "reflection cycle generated no candidates",
                project_root=self._project_root,
                metadata={"reason": "no_candidates"},
            )
        return candidates

    def _collect_context(self) -> _ThinkingContext:
        return _ThinkingContext(
            conversations=self._conversation_context.recent_context(5, 10),
            memories="\n".join(
                f"- [{entry.type}] {entry.title}: {entry.body[:120]}"
                for entry in self._memory_repository.list()[-8:]
            ),
            profile="\n".join(
                f"- [{item.type}] {item.title}: {item.body[:120]}"
                for item in self._profile_repository.list()[:10]
            ),
            sources="\n".join(
                f"- {document.title or document.id}"
                for document in self._source_repository.list_documents()[-5:]
            ),
        )

    def _messages(
        self,
        context: _ThinkingContext,
    ) -> list[SystemMessage | HumanMessage]:
        system = (
            "Generate genuinely new connections, contradictions, questions, "
            "actions, or unnoticed patterns from the supplied private context. "
            "Do not summarize existing content or return generic observations."
        )
        if self._language_preference != "en":
            system += f"\n\nRespond in {self._language_preference}."
        return [
            SystemMessage(content=system),
            HumanMessage(content=context.to_prompt()),
        ]

    @staticmethod
    def _convert(
        output: CandidateListOutput,
        limit: int,
    ) -> list[IdeaCandidate]:
        now = datetime.now(UTC)
        prefix = now.strftime("%Y%m%d-%H%M%S")
        return [
            IdeaCandidate(
                id=f"candidate-{prefix}-{now.microsecond:06d}",
                title=item.title,
                body=item.body,
                candidate_type=item.candidate_type,
                confidence=item.confidence,
                novelty=item.novelty,
                urgency=item.urgency,
                interruption_cost=item.interruption_cost,
                evidence_refs=(),
                suggested_conversation_id=None,
                source_summary="llm-generated",
                created_at=utc_now_iso(),
            )
            for item in output.candidates[:limit]
        ]


@dataclass(frozen=True)
class _ThinkingContext:
    conversations: str
    memories: str
    profile: str
    sources: str

    def is_empty(self) -> bool:
        return not any(
            (self.conversations, self.memories, self.profile, self.sources)
        )

    def to_prompt(self) -> str:
        named = (
            ("Memory entries", self.memories),
            ("Recent conversations", self.conversations),
            ("Personal profile", self.profile),
            ("Source documents", self.sources),
        )
        return "\n\n".join(
            f"## {title}\n{body}" for title, body in named if body
        )
