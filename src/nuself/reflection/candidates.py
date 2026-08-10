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
from nuself.runtime.clock import utc_now_iso
from nuself.agent.endpoint import LangChainLLMEndpoint
from nuself.conversation import ConversationHistoryExcerpt
from nuself.reflection.model import (
    EvidenceExcerpt,
    IdeaCandidate,
    IdeaCandidateType,
)
from nuself.memory.service import MemoryService
from nuself.source.service import SourceService
from nuself.profile.service import ProfileService
from nuself.reflection.audit import REFLECTION_AUDIT


class CandidateItemOutput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    title: str = Field(min_length=1, max_length=80)
    body: str = Field(min_length=1)
    candidate_type: IdeaCandidateType
    confidence: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    urgency: float = Field(ge=0, le=1)
    interruption_cost: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(min_length=1, max_length=6)


class CandidateListOutput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    candidates: list[CandidateItemOutput] = Field(max_length=3)


class ConversationHistoryReader(Protocol):
    def recent(
        self,
        *,
        limit: int = 5,
        messages_per_conversation: int = 10,
    ) -> tuple[ConversationHistoryExcerpt, ...]: ...


class IdeaCandidateGenerator:
    """Generate ideas from explicitly supplied personal-context stores."""

    def __init__(
        self,
        project_root: Path,
        *,
        memory_service: MemoryService,
        source_service: SourceService,
        profile_service: ProfileService,
        conversation_history: ConversationHistoryReader,
        language_preference: str,
        agent: StructuredAgent[CandidateListOutput] | None = None,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
    ) -> None:
        self._project_root = project_root
        self._memory_service = memory_service
        self._source_service = source_service
        self._profile_service = profile_service
        self._conversation_history = conversation_history
        self._agent = agent or default_structured_agent(
            CandidateListOutput,
            project_root=project_root,
            component="reflection",
            endpoints=langchain_models,
        )
        self._language_preference = language_preference

    def generate(self, max_candidates: int = 3) -> list[IdeaCandidate]:
        context = self._collect_context()
        if context.is_empty():
            REFLECTION_AUDIT.write(
                "candidate_generation_skipped",
                "no context available for idea generation",
                project_root=self._project_root,
                metadata={"reason": "empty_context"},
            )
            return []
        try:
            output = self._agent.invoke(self._messages(context))
        except AgentError as exc:
            REFLECTION_AUDIT.failure(
                exc,
                event="candidate_generation_failed",
                message=f"failed to generate candidates: {type(exc).__name__}",
                project_root=self._project_root,
                metadata=None,
            )
            return []
        try:
            candidates = self._convert(
                output,
                max_candidates,
                evidence_catalog=context.evidence_catalog,
            )
        except ValueError as exc:
            REFLECTION_AUDIT.failure(
                exc,
                event="candidate_generation_failed",
                message=f"failed to generate candidates: {type(exc).__name__}",
                project_root=self._project_root,
                metadata=None,
            )
            return []
        if not candidates:
            REFLECTION_AUDIT.write(
                "cycle_no_candidates",
                "reflection cycle generated no candidates",
                project_root=self._project_root,
                metadata={"reason": "no_candidates"},
            )
        return candidates

    def _collect_context(self) -> _ThinkingContext:
        memories = self._memory_service.list_entries()[-8:]
        conversations = self._conversation_history.recent()
        profiles = self._profile_service.list_items()[:10]
        sources = self._source_service.list()[-5:]
        evidence_catalog = {
            **{
                f"memory:{entry.id}": _single_line(
                    f"{entry.title}: {entry.body[:120]}"
                )
                for entry in memories
            },
            **{
                f"conversation:{excerpt.id}": _conversation_excerpt(excerpt)
                for excerpt in conversations
            },
            **{
                f"profile:{item.id}": _single_line(
                    f"{item.title}: {item.body[:120]}"
                )
                for item in profiles
            },
            **{
                f"source:{document.id}": _single_line(
                    document.title or document.id
                )
                for document in sources
            },
        }
        return _ThinkingContext(
            conversations=_render_history(conversations),
            memories="\n".join(
                f"- [memory:{entry.id}] [{entry.type}] {entry.title}: {entry.body[:120]}"
                for entry in memories
            ),
            profile="\n".join(
                f"- [profile:{item.id}] [{item.type}] {item.title}: {item.body[:120]}"
                for item in profiles
            ),
            sources="\n".join(
                f"- [source:{document.id}] {document.title or document.id}"
                for document in sources
            ),
            evidence_catalog=evidence_catalog,
        )

    def _messages(
        self,
        context: _ThinkingContext,
    ) -> list[SystemMessage | HumanMessage]:
        system = (
            "Generate genuinely new connections, contradictions, questions, "
            "actions, or unnoticed patterns from the supplied private context. "
            "Do not summarize existing content or return generic observations."
            " Every candidate must cite one or more bracketed evidence references "
            "from the supplied context; copy those references exactly."
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
        *,
        evidence_catalog: dict[str, str],
    ) -> list[IdeaCandidate]:
        now = datetime.now(UTC)
        prefix = now.strftime("%Y%m%d-%H%M%S")
        candidates: list[IdeaCandidate] = []
        for item in output.candidates[:limit]:
            refs = tuple(dict.fromkeys(item.evidence_refs))
            if any(ref not in evidence_catalog for ref in refs):
                raise ValueError(
                    "candidate cited evidence outside supplied context"
                )
            candidates.append(
                IdeaCandidate(
                    id=f"candidate-{prefix}-{now.microsecond:06d}",
                    title=item.title,
                    body=item.body,
                    candidate_type=item.candidate_type,
                    confidence=item.confidence,
                    novelty=item.novelty,
                    urgency=item.urgency,
                    interruption_cost=item.interruption_cost,
                    evidence_refs=refs,
                    source_summary="derived from " + ", ".join(refs),
                    created_at=utc_now_iso(),
                    evidence_excerpts=tuple(
                        EvidenceExcerpt(ref, evidence_catalog[ref])
                        for ref in refs
                    ),
                )
            )
        return candidates


@dataclass(frozen=True)
class _ThinkingContext:
    conversations: str
    memories: str
    profile: str
    sources: str
    evidence_catalog: dict[str, str]

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


def _render_history(excerpts: tuple[ConversationHistoryExcerpt, ...]) -> str:
    lines: list[str] = []
    for excerpt in excerpts:
        lines.append(f"Conversation [conversation:{excerpt.id}]:")
        lines.extend(
            f"  {message.role}: {message.content[:120]}"
            for message in excerpt.messages
        )
    return "\n".join(lines)


def _conversation_excerpt(excerpt: ConversationHistoryExcerpt) -> str:
    return _single_line(
        " | ".join(
            f"{message.role}: {message.content[:120]}"
            for message in excerpt.messages
        )
    )


def _single_line(value: str, *, limit: int = 240) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"
