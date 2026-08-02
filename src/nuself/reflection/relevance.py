"""LLM-backed relevance evaluation for reflection candidates."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ConfigDict, Field

from nuself.agent.errors import AgentError
from nuself.agent.structured import StructuredAgent, default_structured_agent
from nuself.config.settings import ReflectionSettings
from nuself.reflection.model import IdeaCandidate, RelevanceScore
from nuself.llm import LangChainLLMEndpoint
from nuself.reflection.audit import REFLECTION_AUDIT
from nuself.reflection.repository import ReflectionEntry, ReflectionRepository
from nuself.reflection.schedule_state import ReflectionScheduleStateError
from nuself.runtime.diagnostics import diagnostic_exception_message


class RelevanceScoreOutput(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    passes: bool
    novelty: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    urgency: float = Field(ge=0, le=1)
    interruption_cost: float = Field(ge=0, le=1)
    composite: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1)


class LLMRelevanceGate:
    """Score candidates using explicit schedule and reflection resources."""

    def __init__(
        self,
        project_root: Path,
        config: ReflectionSettings,
        agent: StructuredAgent[RelevanceScoreOutput] | None = None,
        *,
        repository: ReflectionRepository,
        langchain_models: tuple[LangChainLLMEndpoint, ...] | None = None,
    ) -> None:
        self._project_root = project_root
        self._config = config
        self._repository = repository
        self._agent = agent or default_structured_agent(
            RelevanceScoreOutput,
            project_root=project_root,
            component="reflection",
            endpoints=langchain_models,
        )

    def score(self, candidate: IdeaCandidate) -> RelevanceScore:
        cooldown_ok = self._cooldown_ok()
        try:
            output = self._agent.invoke(
                self._messages(
                    candidate,
                    self._repository.list()[:3],
                    cooldown_ok,
                )
            )
        except AgentError as exc:
            return self._fallback(candidate, cooldown_ok, exc)
        try:
            return RelevanceScore(
                passes=output.passes,
                novelty=output.novelty,
                confidence=output.confidence,
                urgency=output.urgency,
                interruption_cost=output.interruption_cost,
                cooldown_ok=cooldown_ok,
                composite=output.composite,
                reasons=(output.reason,),
            )
        except ValueError as exc:
            return self._fallback(candidate, cooldown_ok, exc)

    def _fallback(
        self,
        candidate: IdeaCandidate,
        cooldown_ok: bool,
        error: AgentError | ValueError,
    ) -> RelevanceScore:
        REFLECTION_AUDIT.write(
            "relevance_gate_fallback",
            "Relevance agent failed, using fallback: "
            f"{diagnostic_exception_message(error)}",
            project_root=self._project_root,
        )
        return RelevanceScore(
            passes=False,
            novelty=candidate.novelty,
            confidence=candidate.confidence,
            urgency=candidate.urgency,
            interruption_cost=candidate.interruption_cost,
            cooldown_ok=cooldown_ok,
            composite=0.0,
            reasons=("llm_fallback",),
        )

    def _cooldown_ok(self) -> bool:
        try:
            state = self._repository.schedule_state()
        except ReflectionScheduleStateError as exc:
            REFLECTION_AUDIT.failure(
                exc,
                event="schedule_state_corrupt",
                message=(
                    "Reflection schedule state is invalid; "
                    "cooldown remains active"
                ),
                project_root=self._project_root,
                metadata={"record": "scheduler_state/reflection"},
            )
            return False
        if state is None:
            return True
        elapsed = (datetime.now(UTC) - state.timestamp).total_seconds()
        return elapsed >= self._config.scheduler.cooldown_seconds

    @staticmethod
    def _messages(
        candidate: IdeaCandidate,
        recent: list[ReflectionEntry],
        cooldown_ok: bool,
    ) -> list[SystemMessage | HumanMessage]:
        lines = [
            "Candidate:",
            f"- Title: {candidate.title}",
            f"- Body: {candidate.body}",
            f"- Type: {candidate.candidate_type}",
            (
                "- Original scores: "
                f"confidence={candidate.confidence:.2f}, "
                f"novelty={candidate.novelty:.2f}, "
                f"urgency={candidate.urgency:.2f}, "
                f"interruption={candidate.interruption_cost:.2f}"
            ),
            "",
            "Recent reflections:",
        ]
        lines.extend(
            f"{index}. [{entry.candidate_type}] {entry.title}: {entry.body[:200]}"
            for index, entry in enumerate(recent, start=1)
        )
        if not recent:
            lines.append("None.")
        lines.extend(
            (
                "",
                f"Cooldown active: {'no' if cooldown_ok else 'yes'}",
                f"Time: {datetime.now(UTC).isoformat()}",
            )
        )
        return [
            SystemMessage(
                content=(
                    "Judge whether this reflection is worth surfacing now. "
                    "Return novelty, confidence, urgency, interruption cost, "
                    "composite score, pass decision, and a concise reason."
                )
            ),
            HumanMessage(content="\n".join(lines)),
        ]
